"""Route drift reports into page / digest / log channels.

A :class:`~ledger.report.DriftReport` per tool per day is too granular to hand a
human directly once you watch more than a handful of servers. Routing hard
breaks to an immediate channel and batching soft breaks / semantic flags into a
daily digest keeps the signal-to-noise ratio workable.

Routing rules:

* ``page_immediately`` — structural ``hard_break`` (required rename/removal, etc.)
* ``daily_digest`` — structural ``soft_break`` **or** semantic drift
* ``log_only`` — safe/additive structural noise with no semantic flag

Design article: Turning Reports Into a Review Queue, Not an Alert Flood.
"""

from __future__ import annotations

from ledger.diff import ChangeSeverity
from ledger.report import DriftReport


def route_report(report: DriftReport) -> str:
    """Decide how urgently a human should see this report.

    Args:
        report: Output of :func:`~ledger.report.run_contract_guard`.

    Returns:
        One of ``"page_immediately"``, ``"daily_digest"``, or ``"log_only"``.
    """
    if report.structural_severity == ChangeSeverity.HARD_BREAK:
        return "page_immediately"
    if report.structural_severity == ChangeSeverity.SOFT_BREAK or report.semantic_drift.get(
        "drifted"
    ):
        return "daily_digest"
    return "log_only"


def format_for_digest(report: DriftReport) -> str:
    """Render a Markdown-ish digest block for humans or an Agents SDK triage agent.

    Args:
        report: Drift report to format.

    Returns:
        Multi-line string with a heading plus structural/semantic bullet lines.
    """
    lines = [f"### {report.server_name} / {report.tool_name} ({report.snapshot_date})"]
    for change in report.structural_changes:
        lines.append(
            f"- structural: {change.change_type} on `{change.field_path}` "
            f"({change.before!r} -> {change.after!r}), severity={change.severity.value}"
        )
    if report.semantic_drift.get("drifted"):
        sim = report.semantic_drift.get("mean_similarity")
        if isinstance(sim, (int, float)):
            lines.append(f"- semantic: mean similarity to own history dropped to {sim:.2f}")
        else:
            lines.append("- semantic: drift detected (similarity unavailable)")
    return "\n".join(lines)
