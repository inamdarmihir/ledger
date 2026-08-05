"""Tests for OpenAI Agents SDK adapter helpers (no live network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ledger.agents_adapter import (
    AgentsMCPServerAdapter,
    _coerce_tool_info,
    wrap_agents_mcp_server,
)
from ledger.diff import ChangeSeverity
from ledger.protocols import ToolInfo
from ledger.report import DriftReport
from ledger.routing import format_for_digest


class _FakeAgentsServer:
    """Minimal stand-in for an Agents SDK MCP server with cache invalidation."""

    def __init__(self) -> None:
        self.invalidated = 0
        self.list_calls = 0
        self._tools = [
            SimpleNamespace(
                name="search_customers",
                description="Search customers",
                inputSchema={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ]

    def invalidate_tools_cache(self) -> None:
        self.invalidated += 1

    def list_tools(self) -> list[object]:
        self.list_calls += 1
        return list(self._tools)


def test_wrap_forces_cache_invalidation_on_refresh() -> None:
    server = _FakeAgentsServer()
    client = wrap_agents_mcp_server(server, server_label="crm")

    result = client.list_tools(force_refresh=False)
    assert server.invalidated == 0
    assert server.list_calls == 1
    assert len(result.tools) == 1
    assert result.tools[0].name == "search_customers"
    assert "query" in result.tools[0].input_schema["properties"]

    client.list_tools(force_refresh=True)
    assert server.invalidated == 1
    assert server.list_calls == 2


def test_adapter_accepts_dict_shaped_tools() -> None:
    server = SimpleNamespace(
        list_tools=lambda: [
            {
                "name": "ping",
                "description": "Ping",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]
    )
    adapter = AgentsMCPServerAdapter(server)
    tools = adapter.list_tools(force_refresh=True).tools
    assert tools == [
        ToolInfo(name="ping", description="Ping", input_schema={"type": "object", "properties": {}})
    ]


def test_coerce_tool_info_from_toolinfo_passthrough() -> None:
    t = ToolInfo(name="a", description="b", input_schema={})
    assert _coerce_tool_info(t) is t


def test_coerce_tool_info_rejects_nameless_object() -> None:
    with pytest.raises(TypeError):
        _coerce_tool_info(SimpleNamespace(description="x"))


def test_format_digest_still_works_for_agent_prompt() -> None:
    """Sanity: digests produced for Agents SDK triage stay human-readable."""
    report = DriftReport(
        server_name="crm",
        tool_name="search_customers",
        snapshot_date="2026-07-16",
        structural_changes=[],
        structural_severity=ChangeSeverity.SOFT_BREAK,
        semantic_drift={"drifted": True, "mean_similarity": 0.83},
    )
    text = format_for_digest(report)
    assert "search_customers" in text
    assert "0.83" in text
