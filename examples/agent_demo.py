#!/usr/bin/env python3
"""End-to-end demo: OpenAI Agents SDK agent + Ledger contract guard.

Verified model (OpenAI Agents SDK docs, 2026):
  - Agent model: ``gpt-5.6-sol`` (recommended high-quality Responses-path model)
  - Embeddings: ``text-embedding-3-small`` @ 1536 dims (matches Qdrant collection)

Requires ``OPENAI_API_KEY``. Without it, the script still runs the Ledger pipeline
offline and prints the agent wiring that would be used.
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

from ledger.diff import ChangeSeverity  # noqa: E402
from ledger.report import run_contract_guard  # noqa: E402
from ledger.routing import format_for_digest, route_report  # noqa: E402
from ledger.semantic import ToolDefinitionHistory  # noqa: E402
from ledger.snapshot import SnapshotStore, snapshot_all_servers  # noqa: E402
from mock_mcp import MockMCPClient, search_customers_tool  # noqa: E402

# Latest high-quality model recommended by OpenAI Agents SDK (Python) docs.
AGENT_MODEL = "gpt-5.6-sol"
EMBEDDING_MODEL = "text-embedding-3-small"


def hash_embed(text: str, dims: int = 64) -> list[float]:
    vec = [0.0] * dims
    for i, ch in enumerate(text.lower()):
        vec[(ord(ch) + i) % dims] += 1.0
    for tok in text.lower().replace("-", " ").split():
        vec[hash(tok) % dims] += 2.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def run_ledger_pipeline() -> str:
    """Detect the article's search_customers drift and return a digest string."""
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
    """Ask an Agents SDK agent to triage the Ledger digest."""
    from agents import Agent, ModelSettings, Runner
    from openai.types.shared import Reasoning

    agent = Agent(
        name="MCP Contract Reviewer",
        instructions=(
            "You review Ledger MCP drift digests. Summarize structural vs semantic "
            "signals, say whether on-call should page, and recommend one next action. "
            "Be concise (under 120 words)."
        ),
        model=AGENT_MODEL,
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="low"),
            verbosity="low",
        ),
    )
    result = await Runner.run(
        agent,
        f"Triage this Ledger digest for a customer-facing CRM MCP server:\n\n{digest}",
    )
    print("\n=== Agent triage (gpt-5.6-sol) ===")
    print(result.final_output)


def main() -> None:
    print("=== Ledger + OpenAI Agents SDK end-to-end demo ===")
    print(f"Configured agent model: {AGENT_MODEL}")
    digest = run_ledger_pipeline()

    if not os.getenv("OPENAI_API_KEY"):
        print(
            f"\nSkipping live agent call (set OPENAI_API_KEY to run Agents SDK with {AGENT_MODEL})."
        )
        return

    asyncio.run(run_agent_review(digest))


if __name__ == "__main__":
    main()
