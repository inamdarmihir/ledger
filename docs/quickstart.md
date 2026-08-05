# Quick Start

## 1. Install

```bash
pip install ledger-mcp
docker run -p 6333:6333 qdrant/qdrant
```

## 2. Take your first snapshot

```python
from ledger.snapshot import SnapshotStore

store = SnapshotStore(path=".ledger/snapshots.jsonl")

# tools_list is the result of your MCP client's list_tools() call
store.save_snapshot(
    server_url="https://my-mcp.example.com",
    tools=tools_list,
)
```

## 3. Simulate a schema change and take a second snapshot

Edit your MCP server to remove a required parameter, then:

```python
store.save_snapshot(server_url="https://my-mcp.example.com", tools=new_tools_list)
```

## 4. Run the contract guard

```python
from ledger.report import run_contract_guard
from ledger.memory import build_memory

memory = build_memory()
report = run_contract_guard(store, server_url="https://my-mcp.example.com")
print(report.worst_severity)   # hard_break
for change in report.changes:
    print(change)
```

## 5. Use the CLI

```bash
ledger-mcp diff-pair --before snap1.json --after snap2.json
ledger-mcp report-from-store --store .ledger/snapshots.jsonl --server https://my-mcp.example.com
```

## 6. LangGraph drift pipeline

```python
from ledger.agno_agent import build_langgraph_drift_pipeline

pipeline = build_langgraph_drift_pipeline(store, router=None, memory=memory)
result = pipeline.invoke({
    "server_url": "https://my-mcp.example.com",
    "tool_name": "search_documents",
    "severity": "", "route": "", "notified": False,
})
print(result["route"])   # page_immediately / daily_digest / log_only
```

## 7. Agno triage agent

```python
from ledger.agno_agent import build_agno_triage_agent

agent = build_agno_triage_agent(store, memory=memory)
agent.print_response("Check drift for the search_documents tool and summarise for the digest.")
```
