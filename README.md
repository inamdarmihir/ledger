<div align="center">

# ledger

**MCP tool schema drift detector — know when an upstream server silently changes its contract.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Qdrant](https://img.shields.io/badge/vector--db-Qdrant-red.svg)](https://qdrant.tech)
[![Agno](https://img.shields.io/badge/agent-agno%20v2.8.6-blueviolet.svg)](https://github.com/agno-agi/agno)
[![mem0](https://img.shields.io/badge/memory-mem0%20v3.0.0-green.svg)](https://mem0.ai)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph%20v1.2.10-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-informational.svg)](https://inamdarmihir.github.io/ledger/)

</div>

---

## The Problem

MCP servers change tool schemas without versioning — required parameters become optional, enums gain new values, descriptions shift meaning. Consumer agents break silently at next restart.

## The Solution

**ledger** takes independent daily snapshots of MCP server tool lists, diffs JSON schemas structurally, checks description rewrites for semantic drift via Qdrant embeddings, and routes findings to the right review queue.

## Change Severity

| Severity | Example | Action |
|---|---|---|
| `hard_break` | Required param removed | Page immediately |
| `soft_break` | Param type widened | Daily digest |
| `safe` | Description typo fixed | Log only |
| `none` | No change | Skip |

## How It Works

```
Daily cron / CI
  │
  ▼
snapshot.py — tools/list from each MCP server → JSONL store
  │
  ▼
diff.py — JSON Schema structural comparison
  │
  ▼
semantic.py — description embedding vs Qdrant history (cosine drop)
  │
  ▼
report.py — DriftReport aggregation
  │
  ▼
routing.py — page_immediately | daily_digest | log_only
  └─ mem0 — cross-run drift pattern memory
  └─ agno triage agent — GPT summary for digest queue
```

## Quick Start

```bash
pip install ledger-mcp
docker run -p 6333:6333 qdrant/qdrant
```

```python
from ledger.snapshot import SnapshotStore
from ledger.report import run_contract_guard
from ledger.memory import build_memory

store = SnapshotStore(path=".ledger/snapshots.jsonl")
store.save_snapshot(server_url="https://my-mcp.example.com", tools=tools_list)

memory = build_memory()
report = run_contract_guard(store, server_url="https://my-mcp.example.com")
print(report.worst_severity)   # hard_break / soft_break / safe / none
```

```bash
ledger-mcp diff-pair --before snap1.json --after snap2.json
ledger-mcp report-from-store --store .ledger/snapshots.jsonl
```

## LangGraph Drift Pipeline

```python
from ledger.agno_agent import build_langgraph_drift_pipeline, build_agno_triage_agent

pipeline = build_langgraph_drift_pipeline(store, router, memory=memory)
result = pipeline.invoke({"server_url": "https://my-mcp.example.com", "tool_name": "search"})
print(result["route"])  # page_immediately / daily_digest / log_only
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant instance URL |
| `OPENAI_API_KEY` | — | Required for semantic diff + triage agent |
| `LEDGER_SEMANTIC_THRESHOLD` | `0.9` | Cosine drop below which description drift fires |
| `LEDGER_SNAPSHOT_PATH` | `.ledger/snapshots.jsonl` | JSONL snapshot store path |

## Tech Stack

| Component | Purpose |
|---|---|
| [Qdrant](https://qdrant.tech) `>=1.18.0` | Description embedding history |
| [Agno](https://github.com/agno-agi/agno) `>=2.8.6` | Triage agent |
| [mem0](https://mem0.ai) `>=3.0.0` | Cross-run drift memory |
| [LangGraph](https://langchain-ai.github.io/langgraph/) `>=1.2.10` | detect→route pipeline |

## License

MIT — see [LICENSE](LICENSE).
