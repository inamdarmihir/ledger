#!/usr/bin/env python3
"""Minimal daily contract-guard job wiring (article § Installing and Using Ledger)."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from ledger.report import run_contract_guard  # noqa: E402
from ledger.routing import format_for_digest, route_report  # noqa: E402
from ledger.semantic import ToolDefinitionHistory  # noqa: E402
from ledger.snapshot import SnapshotStore, snapshot_all_servers  # noqa: E402
from mock_mcp import MockMCPClient, search_customers_tool  # noqa: E402


def page_oncall(message: str) -> None:
    print(f"[PAGE]\n{message}\n")


def append_to_digest(message: str) -> None:
    print(f"[DIGEST]\n{message}\n")


def make_embed_fn():
    """Prefer OpenAI text-embedding-3-small when OPENAI_API_KEY is set."""
    if os.getenv("OPENAI_API_KEY"):
        from openai import OpenAI

        from ledger.embeddings import make_openai_embed_fn

        return make_openai_embed_fn(OpenAI()), 1536

    def hash_embed(text: str) -> list[float]:
        dims = 64
        vec = [0.0] * dims
        for i, ch in enumerate(text.lower()):
            vec[(ord(ch) + i) % dims] += 1.0
        for tok in text.split():
            vec[hash(tok) % dims] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    return hash_embed, 64


def main() -> None:
    embed_fn, vector_size = make_embed_fn()
    clients = {
        "crm": MockMCPClient(
            [
                search_customers_tool(
                    description="Search customer records by name or account ID.",
                    limit_default=20,
                )
            ]
        )
    }

    with tempfile.TemporaryDirectory() as tmp:
        store_path = Path(tmp) / "tool_snapshots.jsonl"
        store = SnapshotStore(str(store_path))
        history = ToolDefinitionHistory(
            QdrantClient(location=":memory:"),
            embed_fn=embed_fn,
            vector_size=vector_size,
        )

        # Seed yesterday so today's run can diff.
        snapshot_all_servers(clients, store, "2026-07-15")
        # Mutate schema before today's forced refresh.
        clients["crm"].set_tools(
            [
                search_customers_tool(
                    description=(
                        "Search customer records by name or account ID. "
                        "Use sparingly — this endpoint is now rate-limited."
                    ),
                    limit_default=5,
                )
            ]
        )

        today = date.today().isoformat()
        snapshots = snapshot_all_servers(clients, store, snapshot_date=today)

        # Seed Qdrant with yesterday only so check_drift has priors (demo wiring).
        yday = store.load_history("crm", "search_customers")[0]
        history.record(yday)

        # Guard today's snaps: check_drift sees yesterday, then records today.
        reports = run_contract_guard(store, history, snapshots)

        if not reports:
            print("No drift detected.")
            return

        for report in reports:
            route = route_report(report)
            if route == "page_immediately":
                page_oncall(format_for_digest(report))
            elif route == "daily_digest":
                append_to_digest(format_for_digest(report))


if __name__ == "__main__":
    main()
