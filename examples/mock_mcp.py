"""In-process MCP-client stand-in used by examples and the agent demo."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ledger.protocols import ListToolsResult, ToolInfo


class MockMCPClient:
    """Mutable mock that supports force_refresh=True (Ledger's required contract)."""

    def __init__(self, tools: list[ToolInfo]) -> None:
        self._tools = tools
        self._cached: ListToolsResult | None = None
        self.list_calls = 0
        self.force_refresh_calls = 0

    def set_tools(self, tools: list[ToolInfo]) -> None:
        self._tools = tools
        self._cached = None

    def list_tools(self, *, force_refresh: bool = False) -> ListToolsResult:
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
