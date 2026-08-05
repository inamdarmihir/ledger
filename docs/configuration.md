# Configuration

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant instance URL |
| `OPENAI_API_KEY` | — | Required for semantic diff + Agno triage |
| `LEDGER_SEMANTIC_THRESHOLD` | `0.9` | Cosine below which description drift fires |
| `LEDGER_SNAPSHOT_PATH` | `.ledger/snapshots.jsonl` | JSONL snapshot store path |

## SnapshotStore Parameters

```python
SnapshotStore(
    path: str | Path,               # JSONL file path
    max_snapshots_per_server: int = 30,  # rolling window
)
```

## Routing Rules

| Severity | Default route | Override via |
|---|---|---|
| `hard_break` | `page_immediately` | `routing.py route_report()` |
| `soft_break` | `daily_digest` | custom `RemediationPolicy` |
| `safe` | `log_only` | — |
| `none` | skip | — |

## Semantic Drift Detection

Embeddings are stored per-tool in Qdrant. On each new snapshot, the latest description embedding is compared against the stored cluster. If cosine similarity drops below `LEDGER_SEMANTIC_THRESHOLD`, semantic drift fires regardless of structural diff result.
