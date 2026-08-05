# Setting up Ledger

End-user guide to install Ledger, wire it to your MCP clients (including the
OpenAI Agents SDK), and run the end-to-end demos.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| Python **3.11+** | Typed package (`py.typed`) |
| Optional: **OpenAI API key** | Live embeddings + Agents SDK triage |
| Optional: **Qdrant** | Production semantic layer; demos use `:memory:` |

## 1. Clone and install

```bash
git clone https://github.com/inamdarmihir/ledger.git
cd ledger

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Library only (structural diffs + Qdrant client)
pip install -e .

# Recommended: OpenAI Agents SDK + embeddings
pip install -e ".[openai]"

# Contributors: lint, types, tests
pip install -e ".[dev]"
```

## 2. Environment variables

Copy the example env file and fill in secrets locally (never commit `.env`):

```bash
cp .env.example .env
```

| Variable | Required for | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | Live embeddings / `examples/agent_demo.py` agent call | OpenAI API key |
| `OPENAI_DEFAULT_MODEL` | Optional Agents SDK default | Docs allow `gpt-5.6-sol`; Ledger sets the model on the Agent explicitly |
| `QDRANT_URL` | Production semantic history | e.g. `http://localhost:6333` |

Offline demos (`worked_example.py`, `daily_job.py` without a key) need **no** env vars.

## 3. Verify the install (offline)

```bash
bash scripts/verify.sh
# or step by step:
pytest --cov=ledger
python examples/worked_example.py
python examples/daily_job.py
python examples/agent_demo.py   # skips live agent without OPENAI_API_KEY
```

You should see a `daily_digest` route for `search_customers` with a
`default_changed` soft break (and a semantic signal when history exists).

## 4. Wire Ledger to your MCP clients

Ledger does **not** ship an MCP client. Pass whatever clients your agent
framework already maintains. Each must implement:

```python
def list_tools(self, *, force_refresh: bool = False) -> ListToolsResult: ...
```

When `force_refresh=True`, the client must bypass any `tools/list` cache.

### Plain daily job

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
    QdrantClient(url="http://localhost:6333"),  # or location=":memory:" for trials
    embed_fn=make_openai_embed_fn(OpenAI()),
)

# your_mcp_clients: dict[str, MCPClientLike]
snapshots = snapshot_all_servers(your_mcp_clients, store, date.today().isoformat())
for report in run_contract_guard(store, history, snapshots):
    print(route_report(report), format_for_digest(report), sep="\n")
```

### OpenAI Agents SDK MCP servers

The Agents SDK may set `cache_tools_list=True` for live traffic. Ledger wraps the
same server and busts that cache on its own schedule:

```python
from agents.mcp import MCPServerStreamableHttp
from ledger.agents_adapter import wrap_agents_mcp_server
from ledger import SnapshotStore, snapshot_all_servers

async with MCPServerStreamableHttp(
    name="crm",
    params={"url": "http://localhost:8000/mcp"},
    cache_tools_list=True,  # fine for the agent run loop
) as server:
    clients = {"crm": wrap_agents_mcp_server(server)}
    snapshot_all_servers(clients, SnapshotStore("tool_snapshots.jsonl"), today)
```

`wrap_agents_mcp_server` calls `invalidate_tools_cache()` when
`force_refresh=True`, then `list_tools()`.

### Agents SDK triage of digests

```python
from agents import Runner
from ledger.agents_adapter import build_triage_agent  # model=gpt-5.6-sol

agent = build_triage_agent()
result = await Runner.run(agent, f"Triage this Ledger digest:\n\n{digest}")
print(result.final_output)
```

This matches the [Models](https://openai.github.io/openai-agents-python/models/)
and [Runner](https://openai.github.io/openai-agents-python/ref/run/) guides:
explicit `gpt-5.6-sol` plus `ModelSettings(reasoning=..., verbosity=...)`.

## 5. CLI

```bash
# Structural diff two schema JSON files
ledger-mcp diff-pair before.json after.json

# Digest lines from an existing SnapshotStore JSONL
ledger-mcp report-from-store tool_snapshots.jsonl --semantic
```

## 6. Package map

| Module | Role |
| --- | --- |
| `ledger.snapshot` | `ToolSnapshot`, `SnapshotStore`, `snapshot_all_servers` |
| `ledger.diff` | `diff_schemas`, severity taxonomy |
| `ledger.semantic` | Qdrant `ToolDefinitionHistory` |
| `ledger.report` | `DriftReport`, `run_contract_guard` |
| `ledger.routing` | `route_report`, `format_for_digest` |
| `ledger.priority` | `recommend_cadence` |
| `ledger.embeddings` | OpenAI `text-embedding-3-small` helper |
| `ledger.protocols` | `MCPClientLike` / `ToolInfo` |
| `ledger.agents_adapter` | Agents SDK MCP wrap + triage `Agent` |
| `ledger.cli` | `ledger-mcp` console script |

## 7. Further reading

* Design article (source material): [`docs/article.md`](article.md)
* Examples walkthrough: [`examples/README.md`](../examples/README.md)
* OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
* Agents SDK MCP caching: https://openai.github.io/openai-agents-python/mcp/
* MCP 2026-07-28 caching changelog: https://modelcontextprotocol.io/specification/2026-07-28/changelog
