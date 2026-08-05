"""Agno + LangGraph MCP schema drift triage agent."""
from __future__ import annotations
from typing import Any


def build_agno_triage_agent(snapshot_store, memory=None, model: str = "gpt-4o"):
    """Agno Agent that triages MCP schema drift reports and stores patterns in mem0."""
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    def check_drift(server_url: str, tool_name: str) -> dict[str, Any]:
        """Compare latest vs previous snapshot for a tool and return drift report."""
        from ledger.report import run_contract_guard
        report = run_contract_guard(snapshot_store, server_url=server_url, tool_filter=tool_name)
        if memory and report.changes:
            from ledger.memory import record_drift_event
            for change in report.changes:
                record_drift_event(
                    memory, server_url, tool_name,
                    change.severity.value, str(change)
                )
        return {
            "server": server_url,
            "tool": tool_name,
            "severity": report.worst_severity.value if report.worst_severity else "none",
            "changes": len(report.changes),
        }

    def get_server_history(server_url: str) -> list[dict[str, Any]]:
        """Retrieve historical drift events for a server."""
        if not memory:
            return []
        from ledger.memory import query_drift_history
        return query_drift_history(memory, server_url)

    agent = Agent(
        model=OpenAIChat(id=model),
        name="LedgerTriageAgent",
        description="Monitors MCP tool schema drift and routes breaking changes for human review.",
        instructions=[
            "You monitor MCP server tool schemas for breaking changes.",
            "Check server history before reporting new drift to identify recurring patterns.",
            "Escalate hard_break severity immediately. Log soft_break for daily digest.",
        ],
        tools=[check_drift, get_server_history],
        show_tool_calls=True,
        markdown=True,
    )
    return agent


def build_langgraph_drift_pipeline(snapshot_store, router, memory=None):
    """LangGraph pipeline: snapshot → diff → semantic → route → notify."""
    from typing import TypedDict
    from langgraph.graph import StateGraph, END

    class DriftState(TypedDict):
        server_url: str
        tool_name: str
        severity: str
        route: str
        notified: bool

    def detect_drift(state: DriftState) -> DriftState:
        from ledger.report import run_contract_guard
        report = run_contract_guard(snapshot_store, server_url=state["server_url"], tool_filter=state["tool_name"])
        state["severity"] = report.worst_severity.value if report.worst_severity else "none"
        if memory and report.changes:
            from ledger.memory import record_drift_event
            for ch in report.changes:
                record_drift_event(memory, state["server_url"], state["tool_name"], state["severity"], str(ch))
        return state

    def route_drift(state: DriftState) -> str:
        if state["severity"] == "hard_break":
            return "page"
        elif state["severity"] == "soft_break":
            return "digest"
        return "log"

    def page_node(state: DriftState) -> DriftState:
        state["route"] = "page_immediately"
        state["notified"] = True
        return state

    def digest_node(state: DriftState) -> DriftState:
        state["route"] = "daily_digest"
        state["notified"] = True
        return state

    def log_node(state: DriftState) -> DriftState:
        state["route"] = "log_only"
        state["notified"] = False
        return state

    graph = StateGraph(DriftState)
    graph.add_node("detect", detect_drift)
    graph.add_node("page", page_node)
    graph.add_node("digest", digest_node)
    graph.add_node("log", log_node)
    graph.set_entry_point("detect")
    graph.add_conditional_edges("detect", route_drift, {"page": "page", "digest": "digest", "log": "log"})
    graph.add_edge("page", END)
    graph.add_edge("digest", END)
    graph.add_edge("log", END)
    return graph.compile()
