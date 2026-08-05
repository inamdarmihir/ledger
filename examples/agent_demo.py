#!/usr/bin/env python3
"""End-to-end demo: Ledger contract guard + OpenAI Agents SDK triage agent.

This script follows the official Agents SDK documentation patterns:

* **Models guide** — set ``model="gpt-5.6-sol"`` (recommended high-quality
  Responses-path model) and pass explicit ``ModelSettings`` with
  ``reasoning`` / ``verbosity`` rather than relying on implicit defaults.
* **Runner** — ``await Runner.run(agent, input)`` for the triage turn.
* **Function tools** — optional ``@function_tool`` from
  :func:`ledger.agents_adapter.make_digest_triage_tool`.
* **MCP caching** — live Agents SDK traffic may use ``cache_tools_list=True``;
  Ledger's snapshot path always calls ``list_tools(force_refresh=True)``
  (or ``invalidate_tools_cache()`` via :func:`ledger.agents_adapter.wrap_agents_mcp_server`).

Verified stack
--------------
* Agentic framework: ``openai-agents`` ≥ 0.19.1
* Agent model: ``gpt-5.6-sol``
* Embeddings: ``text-embedding-3-small`` @ 1536 dims

Setup
-----
::

    pip install -e ".[openai]"
    export OPENAI_API_KEY=sk-...
    python examples/agent_demo.py

Without ``OPENAI_API_KEY``, the Ledger pipeline still runs offline (hash
embedder) and the script prints the agent wiring that would be used.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from ledger.agents_adapter import (  # noqa: E402
    DEFAULT_AGENT_MODEL,
    build_triage_agent,
    make_digest_triage_tool,
)
from ledger.diff import ChangeSeverity  # noqa: E402
from ledger.report import run_contract_guard  # noqa: E402
from ledger.routing import format_for_digest, route_report  # noqa: E402
from ledger.semantic import ToolDefinitionHistory  # noqa: E402
from ledger.snapshot import SnapshotStore, snapshot_all_servers  # noqa: E402
from mock_mcp import MockMCPClient, search_customers_tool  # noqa: E402

# Latest high-quality model recommended by OpenAI Agents SDK (Python) docs.
AGENT_MODEL = DEFAULT_AGENT_MODEL
EMBEDDING_MODEL = "text-embedding-3-small"


def hash_embed(text: str, dims: int = 64) -> list[float]:
    """Deterministic offline embedder so description rewrites move the vector."""
    vec = [0.0] * dims
    for i, ch in enumerate(text.lower()):
        vec[(ord(ch) + i) % dims] += 1.0
    for tok in text.lower().replace("-", " ").split():
        vec[hash(tok) % dims] += 2.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def run_ledger_pipeline() -> str:
    """Detect the article's ``search_customers`` drift and return a digest string."""
    yesterday = "Search customer records by name or account ID."
    today = (
        "Search customer records by name or account ID. Use sparingly — "
        "this endpoint is now rate-limited and expensive to call at high volume."
    )
    client = MockMCPClient([search_customers_tool(description=yesterday, limit_default=20)])

    with tempfile.TemporaryDirectory() as tmp:
        store = SnapshotStore(str(Path(tmp) / "snapshots.jsonl"))
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            from openai import OpenAI

            from ledger.embeddings import make_openai_embed_fn

            history = ToolDefinitionHistory(
                QdrantClient(location=":memory:"),
                embed_fn=make_openai_embed_fn(OpenAI(), model=EMBEDDING_MODEL),
                vector_size=1536,
            )
            print(f"Using OpenAI embeddings: {EMBEDDING_MODEL} (1536-d)")
        else:
            history = ToolDefinitionHistory(
                QdrantClient(location=":memory:"),
                embed_fn=hash_embed,
                vector_size=64,
            )
            print("OPENAI_API_KEY unset — using offline hash embedder")

        snap1 = snapshot_all_servers({"crm": client}, store, "2026-07-15")
        run_contract_guard(store, history, snap1)

        client.set_tools([search_customers_tool(description=today, limit_default=5)])
        snap2 = snapshot_all_servers({"crm": client}, store, "2026-07-16")
        reports = run_contract_guard(store, history, snap2)
        assert reports, "expected drift report for search_customers"
        report = reports[0]
        assert report.structural_severity == ChangeSeverity.SOFT_BREAK
        digest = format_for_digest(report)
        print(f"Route: {route_report(report)}")
        print(digest)
        return digest


async def run_agent_review(digest: str) -> None:
    """Ask an Agents SDK agent to triage the Ledger digest.

    Uses :func:`ledger.agents_adapter.build_triage_agent` (``gpt-5.6-sol`` +
    explicit ``ModelSettings``) and attaches a function tool for digest formatting,
    matching the Tools + Models guides.
    """
    from agents import Runner

    agent = build_triage_agent(model=AGENT_MODEL)
    # Attach a function tool so the agent can re-format digests (Agents SDK Tools guide).
    agent.tools = [make_digest_triage_tool()]

    result = await Runner.run(
        agent,
        (
            "Triage this Ledger digest for a customer-facing CRM MCP server.\n"
            "Decide page vs digest vs ignore, and give one next action.\n\n"
            f"{digest}"
        ),
    )
    print(f"\n=== Agent triage ({AGENT_MODEL}) ===")
    print(result.final_output)


def main() -> None:
    """Run Ledger offline, then optionally call the Agents SDK triage agent."""
    print("=== Ledger + OpenAI Agents SDK end-to-end demo ===")
    print(f"Configured agent model: {AGENT_MODEL}")
    print("Agents SDK pattern: Agent(model=..., model_settings=ModelSettings(...)) + Runner.run")
    digest = run_ledger_pipeline()

    if not os.getenv("OPENAI_API_KEY"):
        print(
            f"\nSkipping live agent call (set OPENAI_API_KEY to run Agents SDK with {AGENT_MODEL})."
        )
        print("See docs/SETUP.md for install + environment steps.")
        return

    asyncio.run(run_agent_review(digest))


if __name__ == "__main__":
    main()
