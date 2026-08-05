"""In-process MCP-client stand-in used by examples and the agent demo.

Implements :class:`ledger.protocols.MCPClientLike` with a mutable tool list and
a simple cache that ``force_refresh=True`` clears — the same contract Ledger
expects from a real MCP client or an OpenAI Agents SDK MCP server adapter.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ledger.protocols import ListToolsResult, ToolInfo


class MockMCPClient:
    """Mutable mock that supports ``force_refresh=True`` (Ledger's required contract).

    Attributes:
        list_calls: Total ``list_tools`` invocations.
        force_refresh_calls: Subset of calls that requested a cache bypass.
    """

    def __init__(self, tools: list[ToolInfo]) -> None:
        """Create a mock advertising ``tools``.

        Args:
            tools: Initial tool list returned by ``list_tools``.
        """
        self._tools = tools
        self._cached: ListToolsResult | None = None
        self.list_calls = 0
        self.force_refresh_calls = 0

    def set_tools(self, tools: list[ToolInfo]) -> None:
        """Replace the advertised tool set and drop the cache.

        Args:
            tools: New tool definitions (simulates a server-side release).
        """
        self._tools = tools
        self._cached = None

    def list_tools(self, *, force_refresh: bool = False) -> ListToolsResult:
        """Return tools, honoring or bypassing the in-memory cache.

        Args:
            force_refresh: When ``True``, discard any cached list first.

        Returns:
            Current :class:`ListToolsResult`.
        """
        self.list_calls += 1
        if force_refresh:
            self.force_refresh_calls += 1
            self._cached = None
        if self._cached is None:
            self._cached = ListToolsResult(tools=list(self._tools))
        return self._cached


def search_customers_tool(
    *,
    description: str,
    limit_default: int,
) -> ToolInfo:
    """Build the article's ``search_customers`` tool at a given schema version.

    Args:
        description: Tool description (structural vs semantic demos vary this).
        limit_default: Default for the ``limit`` parameter (worked example: 20→5).

    Returns:
        A :class:`ToolInfo` matching the design article's worked example.
    """
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {
                "type": "integer",
                "default": limit_default,
                "maximum": 100,
            },
        },
        "required": ["query"],
    }
    return ToolInfo(
        name="search_customers",
        description=description,
        input_schema=deepcopy(schema),
    )
