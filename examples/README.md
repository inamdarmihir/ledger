# Ledger examples

Runnable end-to-end demos matching [`docs/article.md`](../docs/article.md) and
the OpenAI Agents SDK setup in [`docs/SETUP.md`](../docs/SETUP.md).

Install first:

```bash
pip install -e .            # offline demos
pip install -e ".[openai]"  # agent_demo live call + OpenAI embeddings
```

| Script | Needs API key? | What it shows |
| --- | --- | --- |
| [`worked_example.py`](worked_example.py) | No | Article scenario: `limit` default 20→5 + description rewrite → soft break + semantic flag → `daily_digest` |
| [`daily_job.py`](daily_job.py) | Optional | Minimal production-shaped wiring: snapshot → guard → page/digest callbacks |
| [`agent_demo.py`](agent_demo.py) | Optional (for live agent) | Ledger pipeline + Agents SDK `Agent`/`Runner` triage with **`gpt-5.6-sol`** |
| [`mock_mcp.py`](mock_mcp.py) | — | Shared `MCPClientLike` test double (`force_refresh=True` clears cache) |

## Recommended order

```bash
python examples/worked_example.py   # understand the signals
python examples/daily_job.py        # see routing callbacks
python examples/agent_demo.py       # Agents SDK triage (offline without key)
```

## Agents SDK notes

`agent_demo.py` uses helpers from `ledger.agents_adapter`:

* `build_triage_agent()` — `Agent(model="gpt-5.6-sol", model_settings=...)`
* `make_digest_triage_tool()` — `@function_tool` for digest formatting
* `wrap_agents_mcp_server()` — adapt SDK MCP servers so Ledger can
  `invalidate_tools_cache()` on its own cadence (see SETUP)

Live agent call:

```bash
export OPENAI_API_KEY=sk-...
python examples/agent_demo.py
```
