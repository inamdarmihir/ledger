"""Protocols for MCP clients Ledger wraps around (Ledger does not ship a client)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolInfo:
    """Minimal tool shape returned by an MCP client's list_tools()."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ListToolsResult:
    tools: list[ToolInfo]


@runtime_checkable
class MCPClientLike(Protocol):
    """Duck-typed MCP client Ledger expects.

    ``list_tools(force_refresh=True)`` must bypass any client-side tools/list
    cache so the monitoring cadence is independent of ttlMs / cacheScope.
    """

    def list_tools(self, *, force_refresh: bool = False) -> ListToolsResult: ...
