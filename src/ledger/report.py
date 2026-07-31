"""Wire structural + semantic layers into per-tool drift reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ledger.diff import ChangeSeverity, StructuralChange, diff_schemas, worst_severity
from ledger.semantic import ToolDefinitionHistory
from ledger.snapshot import SnapshotStore, ToolSnapshot


@dataclass
class DriftReport:
    server_name: str
    tool_name: str
    snapshot_date: str
    structural_changes: list[StructuralChange]
    structural_severity: ChangeSeverity
    semantic_drift: dict[str, Any]


def run_contract_guard(
    store: SnapshotStore,
    history: ToolDefinitionHistory,
    snapshots: list[ToolSnapshot],
) -> list[DriftReport]:
    """Run both layers over every snapshot; flag tools that need human review.

    Never automates a block — neither layer has enough context to act unilaterally.
    """
    reports: list[DriftReport] = []
    for snap in snapshots:
        today, yesterday = store.latest_pair(snap.server_name, snap.tool_name)
        structural_changes = (
            diff_schemas(yesterday.input_schema, today.input_schema) if yesterday and today else []
        )
        semantic = history.check_drift(snap)
        history.record(snap)  # record after checking so today isn't compared to itself

        severity = worst_severity(structural_changes)
        if severity != ChangeSeverity.NONE or semantic["drifted"]:
            reports.append(
                DriftReport(
                    server_name=snap.server_name,
                    tool_name=snap.tool_name,
                    snapshot_date=snap.snapshot_date,
                    structural_changes=structural_changes,
                    structural_severity=severity,
                    semantic_drift=semantic,
                )
            )
    return reports
