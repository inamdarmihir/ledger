"""Route drift reports into page / digest / log channels."""

from __future__ import annotations

from ledger.diff import ChangeSeverity
from ledger.report import DriftReport


def route_report(report: DriftReport) -> str:
    if report.structural_severity == ChangeSeverity.HARD_BREAK:
        return "page_immediately"
    if report.structural_severity == ChangeSeverity.SOFT_BREAK or report.semantic_drift.get(
        "drifted"
    ):
        return "daily_digest"
    return "log_only"


def format_for_digest(report: DriftReport) -> str:
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
