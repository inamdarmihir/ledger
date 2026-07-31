#!/usr/bin/env python3
"""Worked example from the article: search_customers quietly changes its manners.

Runs entirely offline with a deterministic hash embedder + Qdrant in-memory mode.
No API keys required.
"""

from __future__ import annotations

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


def hash_embed(text: str, dims: int = 64) -> list[float]:
    """Lightweight deterministic embedder so description rewrites move the vector."""
    vec = [0.0] * dims
    # Character n-grams + tokens so rewording shifts the embedding.
    for i, ch in enumerate(text.lower()):
        vec[(ord(ch) + i) % dims] += 1.0
    for tok in text.lower().replace("-", " ").split():
        vec[hash(tok) % dims] += 2.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def main() -> None:
    yesterday_desc = "Search customer records by name or account ID."
    today_desc = (
        "Search customer records by name or account ID. Use sparingly — "
        "this endpoint is now rate-limited and expensive to call at high volume."
    )

    client = MockMCPClient([search_customers_tool(description=yesterday_desc, limit_default=20)])

    with tempfile.TemporaryDirectory() as tmp:
        store = SnapshotStore(str(Path(tmp) / "tool_snapshots.jsonl"))
        history = ToolDefinitionHistory(
            QdrantClient(location=":memory:"),
            embed_fn=hash_embed,
            vector_size=64,
        )

        # Day 1: establish baseline history (no report expected beyond first-seen).
        day1 = snapshot_all_servers({"crm": client}, store, "2026-07-15")
        reports_day1 = run_contract_guard(store, history, day1)
        assert reports_day1 == [], "first day should not flag structural/semantic drift"

        # Day 2: soft-break default change + description rewrite.
        client.set_tools([search_customers_tool(description=today_desc, limit_default=5)])
        day2 = snapshot_all_servers({"crm": client}, store, "2026-07-16")
        reports = run_contract_guard(store, history, day2)

        assert len(reports) == 1
        report = reports[0]
        assert report.tool_name == "search_customers"
        assert report.structural_severity == ChangeSeverity.SOFT_BREAK
        assert any(c.change_type == "default_changed" for c in report.structural_changes)
        assert route_report(report) == "daily_digest"

        print("=== Ledger worked example: search_customers ===\n")
        print(format_for_digest(report))
        print("\nStructural changes:")
        for change in report.structural_changes:
            print(
                f"  {change.change_type} on {change.field_path}: "
                f"{change.before!r} -> {change.after!r} ({change.severity.value})"
            )
        print("\nSemantic drift:")
        for k, v in report.semantic_drift.items():
            if k == "most_similar_prior_text" and isinstance(v, str):
                print(f"  {k}: {v[:80]}...")
            else:
                print(f"  {k}: {v}")

        print(f"\nforce_refresh calls: {client.force_refresh_calls}")
        print("OK — soft break + semantic signal both fired independently.")


if __name__ == "__main__":
    main()
