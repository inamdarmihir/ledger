# API Reference

## run_contract_guard

```python
from ledger.report import run_contract_guard

report = run_contract_guard(
    store: SnapshotStore,
    server_url: str,
    tool_filter: str | None = None,
) -> DriftReport
# DriftReport: changes, worst_severity, server_url, timestamp
```

## SnapshotStore

```python
store.save_snapshot(server_url: str, tools: list[ToolInfo])
store.latest_pair(server_url: str) -> tuple[ToolSnapshot, ToolSnapshot] | None
store.list_servers() -> list[str]
```

## diff_schemas

```python
from ledger.diff import diff_schemas

changes = diff_schemas(old_schema: dict, new_schema: dict) -> list[StructuralChange]
# StructuralChange: field, change_type, severity, old_value, new_value
```

## Memory

```python
from ledger.memory import build_memory, record_drift_event, query_drift_history

memory = build_memory(qdrant_url, collection_name)
record_drift_event(memory, server, tool, severity, description)
query_drift_history(memory, server) -> list[dict]
```

## Agno + LangGraph

```python
from ledger.agno_agent import build_agno_triage_agent, build_langgraph_drift_pipeline

agent = build_agno_triage_agent(snapshot_store, memory=None, model="gpt-4o")
pipeline = build_langgraph_drift_pipeline(snapshot_store, router, memory=None)
```
