"""Wire structural + semantic layers into per-tool drift reports.

The daily job runs both layers over every snapshot and produces one flagged item
per tool that needs a human's attention — never an automated block, since neither
layer has enough context to safely act unilaterally.

Both flags can fire independently on the same tool for entirely different reasons
(the worked example's ``search_customers`` default change + description rewrite).

Design article: Wiring It Together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ledger.diff import ChangeSeverity, StructuralChange, diff_schemas, worst_severity
from ledger.semantic import ToolDefinitionHistory
from ledger.snapshot import SnapshotStore, ToolSnapshot


@dataclass
class DriftReport:
    """Human-reviewable finding for one tool on one snapshot date.

    Attributes:
        server_name: MCP server label.
        tool_name: Tool that drifted.
        snapshot_date: ISO date of the snapshot that triggered the report.
        structural_changes: List from :func:`~ledger.diff.diff_schemas`.
        structural_severity: Worst severity among structural changes.
        semantic_drift: Result dict from
            :meth:`~ledger.semantic.ToolDefinitionHistory.check_drift`.
    """

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

    For each snapshot:

    1. Structural-diff today's schema against yesterday's (if any).
    2. Semantic-check today's definition against Qdrant history.
    3. Record today's embedding *after* the check so it is not compared to itself.
    4. Emit a :class:`DriftReport` only when something needs attention.

    Never automates a block — route reports with :func:`ledger.routing.route_report`.

    Args:
        store: Snapshot log containing at least ``snapshots`` (and priors).
        history: Qdrant-backed definition history.
        snapshots: Snapshots from the current run (e.g. from
            :func:`~ledger.snapshot.snapshot_all_servers`).

    Returns:
        Drift reports for tools with structural and/or semantic signals.
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
