"""OpenAI Agents SDK integration helpers for Ledger.

The Agents SDK is the verified agentic framework for this repository
(``openai-agents`` ≥ 0.19.1). Its MCP docs recommend ``cache_tools_list=True``
when tool definitions are stable — which is exactly the consumer-side blind
spot Ledger monitors with an independent ``force_refresh`` snapshot cadence.

This module is optional (requires ``pip install -e ".[openai]"``) and provides:

1. :func:`wrap_agents_mcp_server` — adapt an Agents SDK MCP server so it
   satisfies Ledger's :class:`~ledger.protocols.MCPClientLike` protocol.
   On ``force_refresh=True`` it calls ``invalidate_tools_cache()`` when present,
   then ``list_tools()``.
2. :func:`build_triage_agent` — construct an Agents SDK ``Agent`` configured
   with the docs-recommended high-quality model ``gpt-5.6-sol`` and explicit
   ``ModelSettings`` (Responses path).
3. :func:`make_digest_triage_tool` — a ``@function_tool`` that formats a
   :class:`~ledger.report.DriftReport` for agent consumption.

Official references:

* Models: https://openai.github.io/openai-agents-python/models/
* MCP caching: https://openai.github.io/openai-agents-python/mcp/
* Tools: https://openai.github.io/openai-agents-python/tools/
"""

from __future__ import annotations

from typing import Any

from ledger.protocols import ListToolsResult, ToolInfo
from ledger.report import DriftReport
from ledger.routing import format_for_digest, route_report

# Docs-recommended high-quality Responses-path model (Agents SDK Models guide).
DEFAULT_AGENT_MODEL = "gpt-5.6-sol"


class AgentsMCPServerAdapter:
    """Adapt an OpenAI Agents SDK MCP server to :class:`MCPClientLike`.

    The wrapped server must expose an awaitable or sync ``list_tools()`` method.
    When the server supports ``invalidate_tools_cache()``, Ledger calls it before
    listing so monitoring bypasses ``cache_tools_list``.

    Note:
        Agents SDK MCP servers are typically async. This adapter runs
        ``list_tools`` synchronously via :func:`asyncio.run` when it receives a
        coroutine, which is appropriate for Ledger's daily job (not for use
        inside an already-running event loop — call the async helpers from your
        own async job in that case).
    """

    def __init__(self, server: Any, *, server_label: str | None = None) -> None:
        """Wrap an Agents SDK MCP server instance.

        Args:
            server: ``MCPServerStdio``, ``MCPServerSse``,
                ``MCPServerStreamableHttp``, or any object with ``list_tools``.
            server_label: Optional label used only in error messages.
        """
        self._server = server
        self._server_label = server_label or getattr(server, "name", type(server).__name__)

    def list_tools(self, *, force_refresh: bool = False) -> ListToolsResult:
        """List tools, optionally invalidating the Agents SDK tools cache first.

        Args:
            force_refresh: When ``True``, call ``invalidate_tools_cache()`` if
                available, then fetch a fresh tool list.

        Returns:
            Ledger :class:`ListToolsResult` built from the SDK tool objects.
        """
        if force_refresh:
            invalidate = getattr(self._server, "invalidate_tools_cache", None)
            if callable(invalidate):
                invalidate()

        raw = self._server.list_tools()
        tools_list = _resolve_maybe_awaitable(raw)
        return ListToolsResult(tools=[_coerce_tool_info(t) for t in tools_list])


def wrap_agents_mcp_server(
    server: Any, *, server_label: str | None = None
) -> AgentsMCPServerAdapter:
    """Return a Ledger-compatible client wrapping an Agents SDK MCP server.

    Example (async context manager from the Agents SDK MCP docs)::

        from agents.mcp import MCPServerStreamableHttp
        from ledger.agents_adapter import wrap_agents_mcp_server
        from ledger import SnapshotStore, snapshot_all_servers

        async with MCPServerStreamableHttp(
            name="crm",
            params={"url": "http://localhost:8000/mcp"},
            cache_tools_list=True,  # fine for live agent traffic
        ) as server:
            clients = {"crm": wrap_agents_mcp_server(server)}
            # Ledger forces a cache-busting refresh on its own schedule:
            snapshot_all_servers(clients, store, snapshot_date=today)

    Args:
        server: Agents SDK MCP server instance.
        server_label: Optional label for error messages.

    Returns:
        An :class:`AgentsMCPServerAdapter`.
    """
    return AgentsMCPServerAdapter(server, server_label=server_label)


def build_triage_agent(
    *,
    model: str = DEFAULT_AGENT_MODEL,
    name: str = "MCP Contract Reviewer",
) -> Any:
    """Build an Agents SDK ``Agent`` that triages Ledger digests.

    Follows the Models guide pattern: set ``model="gpt-5.6-sol"`` explicitly and
    pass ``ModelSettings`` with ``reasoning`` / ``verbosity`` rather than relying
    on implicit defaults.

    Args:
        model: Model id (default ``gpt-5.6-sol``).
        name: Agent display name.

    Returns:
        A configured ``agents.Agent`` instance.

    Raises:
        ImportError: If ``openai-agents`` is not installed.
    """
    try:
        from agents import Agent, ModelSettings
        from openai.types.shared import Reasoning
    except ImportError as exc:  # pragma: no cover - exercised in optional extra
        raise ImportError(
            "openai-agents is required for build_triage_agent(). "
            'Install with: pip install -e ".[openai]"'
        ) from exc

    return Agent(
        name=name,
        instructions=(
            "You review Ledger MCP drift digests for engineering on-call. "
            "Summarize structural vs semantic signals, say whether on-call should "
            "page, and recommend one concrete next action. Be concise (under 120 words)."
        ),
        model=model,
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="low"),
            verbosity="low",
        ),
    )


def make_digest_triage_tool() -> Any:
    """Create an Agents SDK function tool that formats a drift report digest.

    The returned tool can be attached to an ``Agent(tools=[...])`` so the model
    can request a normalized digest string during a broader review workflow.

    Returns:
        An Agents SDK function tool (from ``agents.function_tool``).

    Raises:
        ImportError: If ``openai-agents`` is not installed.
    """
    try:
        from agents import function_tool
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "openai-agents is required for make_digest_triage_tool(). "
            'Install with: pip install -e ".[openai]"'
        ) from exc

    @function_tool
    def format_ledger_digest(
        server_name: str,
        tool_name: str,
        snapshot_date: str,
        structural_severity: str,
        semantic_drifted: bool,
        mean_similarity: float | None = None,
        structural_summary: str = "",
    ) -> str:
        """Format a Ledger-style digest line for human or agent review.

        Args:
            server_name: MCP server label.
            tool_name: Tool that changed.
            snapshot_date: ISO date of the finding.
            structural_severity: One of hard_break / soft_break / safe / none.
            semantic_drifted: Whether the semantic layer flagged drift.
            mean_similarity: Optional mean cosine similarity to own history.
            structural_summary: Optional free-text structural change summary.
        """
        from ledger.diff import ChangeSeverity

        try:
            severity = ChangeSeverity(structural_severity)
        except ValueError:
            severity = ChangeSeverity.NONE

        report = DriftReport(
            server_name=server_name,
            tool_name=tool_name,
            snapshot_date=snapshot_date,
            structural_changes=[],
            structural_severity=severity,
            semantic_drift={
                "drifted": semantic_drifted,
                "mean_similarity": mean_similarity,
                "reason": "semantic_drift" if semantic_drifted else "stable",
            },
        )
        header = format_for_digest(report)
        route = route_report(report)
        extra = f"\n- structural_summary: {structural_summary}" if structural_summary else ""
        return f"[route={route}]\n{header}{extra}"

    return format_ledger_digest


def _resolve_maybe_awaitable(value: Any) -> Any:
    """Return ``value`` or run it if it is a coroutine / awaitable list result."""
    import asyncio
    import inspect

    if inspect.iscoroutine(value):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(value)
        raise RuntimeError(
            "AgentsMCPServerAdapter.list_tools() cannot await inside a running "
            "event loop. From async code, call `await server.list_tools()` "
            "yourself and map results with ledger.protocols.ToolInfo, or run "
            "the snapshot job in a sync context."
        )
    if inspect.isawaitable(value):
        raise TypeError(
            f"Unsupported awaitable from list_tools(): {type(value)!r}. "
            "Expected a coroutine or a plain list/result."
        )
    return value


def _coerce_tool_info(tool: Any) -> ToolInfo:
    """Map an Agents SDK / MCP tool object (or dict) to :class:`ToolInfo`."""
    if isinstance(tool, ToolInfo):
        return tool
    if isinstance(tool, dict):
        return ToolInfo(
            name=str(tool.get("name", "")),
            description=str(tool.get("description", "") or ""),
            input_schema=dict(tool.get("inputSchema") or tool.get("input_schema") or {}),
        )

    name = getattr(tool, "name", None) or getattr(tool, "tool_name", None)
    description = getattr(tool, "description", None) or ""
    schema = (
        getattr(tool, "input_schema", None)
        or getattr(tool, "inputSchema", None)
        or getattr(tool, "parameters", None)
        or {}
    )
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump()
    elif not isinstance(schema, dict):
        schema = dict(schema) if schema else {}

    if not name:
        raise TypeError(f"Cannot coerce tool object to ToolInfo: {type(tool)!r}")
    return ToolInfo(name=str(name), description=str(description), input_schema=dict(schema))
