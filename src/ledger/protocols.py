"""Protocols for MCP clients Ledger wraps around.

Ledger does **not** ship an MCP client. It duck-types whatever client your
agent framework already maintains (including OpenAI Agents SDK MCP servers —
see ``ledger.agents_adapter``).

The only required method is::

    list_tools(*, force_refresh: bool = False) -> ListToolsResult

When ``force_refresh=True``, the client **must** bypass any client-side
``tools/list`` cache (``ttlMs`` / ``cacheScope`` / Agents SDK
``cache_tools_list``). That independence is the whole point of Ledger's
monitoring cadence: live agent traffic may honor cache hints; the snapshot job
must not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolInfo:
    """Minimal tool shape returned by an MCP client's ``list_tools()``.

    Attributes:
        name: Tool name as advertised by the server (e.g. ``search_customers``).
        description: Human/model-facing description text. Used both for display
            and (flattened into ``raw_definition``) for semantic embeddings.
        input_schema: JSON Schema object describing tool arguments. This is the
            surface the structural differ walks.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ListToolsResult:
    """Result of a ``tools/list`` call, matching MCP's list shape at minimum.

    Attributes:
        tools: Tools currently advertised by the server.
    """

    tools: list[ToolInfo]


@runtime_checkable
class MCPClientLike(Protocol):
    """Duck-typed MCP client Ledger expects.

    ``list_tools(force_refresh=True)`` must bypass any client-side tools/list
    cache so the monitoring cadence is independent of ``ttlMs`` / ``cacheScope``.

    Implementations may wrap:

    * Your own MCP SDK client
    * OpenAI Agents SDK ``MCPServerStdio`` / ``MCPServerSse`` /
      ``MCPServerStreamableHttp`` via :func:`ledger.agents_adapter.wrap_agents_mcp_server`
    * A test double such as ``examples.mock_mcp.MockMCPClient``
    """

    def list_tools(self, *, force_refresh: bool = False) -> ListToolsResult:
        """Return the server's current tool list.

        Args:
            force_refresh: When ``True``, ignore any cached ``tools/list``
                response and fetch live from the server.

        Returns:
            A :class:`ListToolsResult` with the current tool definitions.
        """
        ...
