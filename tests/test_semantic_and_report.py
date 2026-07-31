"""Semantic history + contract guard wiring tests (Qdrant local mode)."""

from __future__ import annotations

from pathlib import Path

from qdrant_client import QdrantClient

from ledger.diff import ChangeSeverity
from ledger.report import run_contract_guard
from ledger.routing import format_for_digest, route_report
from ledger.semantic import ToolDefinitionHistory
from ledger.snapshot import SnapshotStore, build_snapshot


def _embed(text: str, dims: int = 32) -> list[float]:
    vec = [0.0] * dims
    for i, ch in enumerate(text.lower()):
        vec[(ord(ch) + i) % dims] += 1.0
    for tok in text.lower().replace("-", " ").split():
        vec[hash(tok) % dims] += 3.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def test_check_drift_no_history_yet() -> None:
    history = ToolDefinitionHistory(
        QdrantClient(location=":memory:"),
        embed_fn=lambda t: _embed(t),
        vector_size=32,
    )
    snap = build_snapshot(
        "crm",
        "search_customers",
        "Search customer records by name or account ID.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        "2026-07-15",
    )
    result = history.check_drift(snap)
    assert result["drifted"] is False
    assert result["reason"] == "no_history_yet"


def test_worked_example_end_to_end(tmp_path: Path) -> None:
    store = SnapshotStore(str(tmp_path / "tool_snapshots.jsonl"))
    history = ToolDefinitionHistory(
        QdrantClient(location=":memory:"),
        embed_fn=lambda t: _embed(t),
        vector_size=32,
    )

    yesterday_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 20, "maximum": 100},
        },
        "required": ["query"],
    }
    today_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5, "maximum": 100},
        },
        "required": ["query"],
    }

    day1 = build_snapshot(
        "crm",
        "search_customers",
        "Search customer records by name or account ID.",
        yesterday_schema,
        "2026-07-15",
    )
    store.append(day1)
    assert run_contract_guard(store, history, [day1]) == []

    day2 = build_snapshot(
        "crm",
        "search_customers",
        (
            "Search customer records by name or account ID. Use sparingly — "
            "this endpoint is now rate-limited and expensive to call at high volume."
        ),
        today_schema,
        "2026-07-16",
    )
    store.append(day2)
    reports = run_contract_guard(store, history, [day2])
    assert len(reports) == 1
    report = reports[0]
    assert report.structural_severity == ChangeSeverity.SOFT_BREAK
    assert any(
        c.change_type == "default_changed" and c.before == 20 and c.after == 5
        for c in report.structural_changes
    )
    # Semantic layer may or may not flag depending on hash embed distance; both
    # independent signals are valid. Soft break alone routes to daily_digest.
    assert route_report(report) == "daily_digest"
    digest = format_for_digest(report)
    assert "search_customers" in digest
    assert "default_changed" in digest


def test_hard_break_routes_to_page() -> None:
    from ledger.diff import StructuralChange
    from ledger.report import DriftReport

    report = DriftReport(
        server_name="crm",
        tool_name="search_customers",
        snapshot_date="2026-07-16",
        structural_changes=[
            StructuralChange(
                "query", "required_field_removed", ChangeSeverity.HARD_BREAK, "query", None
            )
        ],
        structural_severity=ChangeSeverity.HARD_BREAK,
        semantic_drift={"drifted": False},
    )
    assert route_report(report) == "page_immediately"
