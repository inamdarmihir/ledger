"""Schema drift pattern memory backed by mem0 + Qdrant."""
from __future__ import annotations
from typing import Any


def build_memory(qdrant_url: str = "http://localhost:6333", collection_name: str = "ledger_memory"):
    from mem0 import Memory
    return Memory.from_config({
        "vector_store": {
            "provider": "qdrant",
            "config": {"url": qdrant_url, "collection_name": collection_name},
        }
    })


def record_drift_event(memory, server: str, tool: str, severity: str, description: str, agent_id: str = "ledger") -> None:
    """Persist a schema drift event for trend analysis."""
    memory.add(
        f"MCP server '{server}' tool '{tool}': {severity} drift — {description}",
        user_id=agent_id,
        metadata={"server": server, "tool": tool, "severity": severity},
    )


def query_drift_history(memory, server: str, agent_id: str = "ledger") -> list[dict[str, Any]]:
    """Retrieve past drift events for a server."""
    results = memory.search(f"schema drift for MCP server {server}", user_id=agent_id)
    return results.get("results", [])
