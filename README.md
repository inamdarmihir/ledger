# Ledger

**Consumer-side contract guard for MCP tool-schema drift.**

Ledger watches Model Context Protocol servers you *consume but do not control*. It takes an independent daily `tools/list` snapshot (bypassing client-side cache TTLs), diffs each tool’s JSON Schema structurally, and checks description rewrites for semantic drift in Qdrant. Findings go to a human review queue — never an automated block.

This repository is an end-to-end implementation of the design in [`docs/article.md`](docs/article.md).

---

## Why it exists

MCP’s 2026-07-28 revision added caching hints (`ttlMs`, `cacheScope`) on `tools/list`. That is a real efficiency win for stable tool surfaces — and it widens the window during which a client can keep reasoning against a schema the server has already moved past.

Ledger closes that blind spot from the consumer side:

| Layer | Catches | Mechanism |
| --- | --- | --- |
| **Structural diff** | Renames, type changes, enum narrowing, default changes, required/optional flips | Deterministic JSON Schema walk |
| **Semantic drift** | Description rewrites that leave the schema shape untouched | Per-tool embedding history in Qdrant |

## Package layout

```
ledger/
├── snapshot.py      # ToolSnapshot, SnapshotStore, snapshot_all_servers()
├── diff.py          # diff_schemas(), StructuralChange, worst_severity()
├── semantic.py      # ToolDefinitionHistory (Qdrant-backed drift check)
├── report.py        # DriftReport, run_contract_guard()
├── routing.py       # route_report(), format_for_digest()
├── priority.py      # recommend_cadence()
├── embeddings.py    # OpenAI text-embedding-3-small helper
└── protocols.py     # MCPClientLike protocol (Ledger wraps your client)
```

## Verified models & stack

| Concern | Choice | Verified |
| --- | --- | --- |
| Agentic framework | [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) (`openai-agents` ≥ 0.19.1) | Docs recommend **`gpt-5.6-sol`** for higher-quality agent work on the Responses path |
| Embeddings | OpenAI **`text-embedding-3-small`** | Default **1536** dimensions — matches Ledger’s Qdrant collection |
| Vector store | [Qdrant](https://qdrant.tech/documentation/) via `qdrant-client` ≥ 1.18.0 | Uses `query_points` + `PointStruct` (current Query API) |
| Python | 3.11+ | Typed package (`py.typed`) |

Set `OPENAI_API_KEY` to exercise live embeddings / the Agents SDK demo. All unit tests and the worked example run offline with a deterministic hash embedder and Qdrant `:memory:` mode.

## Install

```bash
# Library only (structural + Qdrant semantic layers)
pip install -e .

# With OpenAI Agents SDK + embeddings
pip install -e ".[openai]"

# Dev: tests, ruff, mypy
pip install -e ".[dev]"
```

## Quick start

```python
from datetime import date
from qdrant_client import QdrantClient
from openai import OpenAI

from ledger import (
    SnapshotStore,
    ToolDefinitionHistory,
    snapshot_all_servers,
    run_contract_guard,
    route_report,
    format_for_digest,
)
from ledger.embeddings import make_openai_embed_fn

store = SnapshotStore(path="tool_snapshots.jsonl")
history = ToolDefinitionHistory(
    QdrantClient(url="http://localhost:6333"),
    embed_fn=make_openai_embed_fn(OpenAI()),  # text-embedding-3-small @ 1536-d
)

# your_mcp_clients: dict[str, MCPClientLike] with list_tools(force_refresh=True)
snapshots = snapshot_all_servers(your_mcp_clients, store, snapshot_date=date.today().isoformat())
reports = run_contract_guard(store, history, snapshots)

for report in reports:
    route = route_report(report)
    if route == "page_immediately":
        page_oncall(format_for_digest(report))
    elif route == "daily_digest":
        append_to_digest(format_for_digest(report))
```

Ledger does **not** ship an MCP client. It wraps whatever client your agent framework already maintains and always calls `list_tools(force_refresh=True)` so monitoring is independent of `ttlMs`.

### CLI

```bash
# Structural diff two schema JSON files
ledger-mcp diff-pair before.json after.json

# Emit routing + digest lines from an existing SnapshotStore JSONL
ledger-mcp report-from-store tool_snapshots.jsonl --semantic
```

## End-to-end examples

```bash
# Article worked example (offline, no API key)
python examples/worked_example.py

# Daily job wiring (offline hash embedder, or OpenAI if keyed)
python examples/daily_job.py

# Agents SDK triage with gpt-5.6-sol (needs OPENAI_API_KEY for live agent call)
python examples/agent_demo.py
```

### Worked example (summary)

`search_customers(query, limit=20)` quietly becomes `limit=5` and the description warns about rate limits. Ledger reports:

- **Structural:** `default_changed` on `limit.default` → `soft_break`
- **Semantic:** mean similarity to the tool’s own history drops below the floor
- **Route:** `daily_digest` (hard breaks page immediately)

## Severity taxonomy

| Change | Severity |
| --- | --- |
| Required field removed / renamed away | `hard_break` |
| Optional → required, type change | `hard_break` |
| Enum narrowed, default changed, bounds tightened | `soft_break` |
| Optional field added, enum widened | `safe` |
| Description-only rewrite | structural `none` + possible semantic flag |

## Development

```bash
pip install -e ".[dev]"

# Lint
ruff check src tests examples
ruff format --check src tests examples

# Types
mypy

# Tests
pytest --cov=ledger --cov-report=term-missing

# Or one shot
bash scripts/verify.sh
```

## Architecture

```
Daily snapshot job ──force tools/list──▶ SnapshotStore (JSONL)
        │                                      │
        │                         ┌────────────┴────────────┐
        │                         ▼                         ▼
        │                  Structural diff           Embed → Qdrant
        │                  (hard/soft/safe)          (per-tool history)
        │                         │                         │
        └─────────────────────────┴────────────┬────────────┘
                                               ▼
                                        DriftReport → route
                                   (page / digest / log_only)
```

## Documentation

- Design article (source material): [`docs/article.md`](docs/article.md)
- MCP caching (2026-07-28): [specification changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
- OpenAI Agents SDK models: [Models guide](https://openai.github.io/openai-agents-python/models/)
- Qdrant Query API: [Search docs](https://qdrant.tech/documentation/search/search/)

## License

MIT — see [`LICENSE`](LICENSE).
