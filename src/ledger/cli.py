"""Minimal CLI for running the contract guard against a JSONL snapshot log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient

from ledger.diff import ChangeSeverity, diff_schemas, worst_severity
from ledger.report import DriftReport
from ledger.routing import format_for_digest, route_report
from ledger.snapshot import SnapshotStore


def _hash_embed(text: str, dims: int = 32) -> list[float]:
    """Deterministic bag-of-words embedding for offline CLI demos (not production)."""
    vec = [0.0] * dims
    tokens = text.lower().split()
    if not tokens:
        return vec
    for tok in tokens:
        vec[hash(tok) % dims] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ledger-mcp",
        description="Consumer-side MCP tool-schema drift guard",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    diff_p = sub.add_parser("diff-pair", help="Structurally diff two schema JSON files")
    diff_p.add_argument("before", type=Path)
    diff_p.add_argument("after", type=Path)

    run_p = sub.add_parser(
        "report-from-store",
        help="Emit digest lines for latest pairs in a SnapshotStore JSONL",
    )
    run_p.add_argument("store", type=Path, help="Path to tool_snapshots.jsonl")
    run_p.add_argument(
        "--semantic",
        action="store_true",
        help="Also run offline hash-embedding semantic check (demo only)",
    )
    return parser


def _cmd_diff_pair(before: Path, after: Path) -> int:
    before_schema = json.loads(before.read_text(encoding="utf-8"))
    after_schema = json.loads(after.read_text(encoding="utf-8"))
    changes = diff_schemas(before_schema, after_schema)
    severity = worst_severity(changes)
    payload = {
        "severity": severity.value,
        "changes": [
            {
                "field_path": c.field_path,
                "change_type": c.change_type,
                "severity": c.severity.value,
                "before": c.before,
                "after": c.after,
            }
            for c in changes
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0 if severity != ChangeSeverity.HARD_BREAK else 2


def _cmd_report_from_store(store_path: Path, *, semantic: bool) -> int:
    store = SnapshotStore(str(store_path))
    tools = store.known_tools()
    if not tools:
        print("No snapshots found.", file=sys.stderr)
        return 1

    history = None
    if semantic:
        from ledger.semantic import ToolDefinitionHistory

        history = ToolDefinitionHistory(
            QdrantClient(location=":memory:"),
            embed_fn=lambda t: _hash_embed(t),
            vector_size=32,
        )
        # Seed history with all but the latest snapshot per tool so check_drift has priors.
        for server, tool in tools:
            hist = store.load_history(server, tool)
            for snap in hist[:-1]:
                history.record(snap)

    exit_code = 0
    for server, tool in tools:
        today, yesterday = store.latest_pair(server, tool)
        if today is None:
            continue
        structural = diff_schemas(yesterday.input_schema, today.input_schema) if yesterday else []
        severity = worst_severity(structural)
        semantic_drift: dict[str, object] = {
            "drifted": False,
            "reason": "skipped",
            "mean_similarity": None,
        }
        if history is not None:
            semantic_drift = history.check_drift(today)
            history.record(today)

        if severity == ChangeSeverity.NONE and not semantic_drift.get("drifted"):
            continue
        report = DriftReport(
            server_name=server,
            tool_name=tool,
            snapshot_date=today.snapshot_date,
            structural_changes=structural,
            structural_severity=severity,
            semantic_drift=semantic_drift,
        )
        print(f"[{route_report(report)}]\n{format_for_digest(report)}\n")
        if severity == ChangeSeverity.HARD_BREAK:
            exit_code = 2
    return exit_code


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "diff-pair":
        raise SystemExit(_cmd_diff_pair(args.before, args.after))
    if args.command == "report-from-store":
        raise SystemExit(_cmd_report_from_store(args.store, semantic=args.semantic))
    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
