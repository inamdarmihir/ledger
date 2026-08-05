"""Deterministic structural JSON-Schema diff for MCP tool input schemas.

Given two snapshots of the same tool, most interesting changes can be classified
without embeddings: renames, type changes, enum narrowing, default changes, and
required/optional flips.

Severity taxonomy (design article — What "Breaking" Means for a Tool Schema):

* ``hard_break`` — previously-valid calls will now fail outright
  (required field removed/renamed, optional→required, type change).
* ``soft_break`` — some previously-valid calls may fail or behave differently
  (enum narrowed, default changed, bounds tightened, required→optional).
* ``safe`` — additive; does not invalidate prior calls
  (optional field added, enum widened).
* ``none`` — no structural changes detected.

This module handles flat, top-level parameters — the common case for MCP tools.
Nested ``object`` / ``array`` schemas and ``oneOf`` / ``anyOf`` unions need the
same walk applied recursively; the classification scheme stays the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ChangeSeverity(StrEnum):
    """How dangerous a structural schema change is for existing callers."""

    HARD_BREAK = "hard_break"
    SOFT_BREAK = "soft_break"
    SAFE = "safe"
    NONE = "none"


@dataclass
class StructuralChange:
    """One classified difference between yesterday's and today's schema.

    Attributes:
        field_path: Dot-path to the changed field (e.g. ``limit.default``).
        change_type: Machine-readable change kind (e.g. ``default_changed``).
        severity: :class:`ChangeSeverity` for this individual change.
        before: Prior value (or field name / ``None`` for additions).
        after: New value (or field name / ``None`` for removals).
    """

    field_path: str
    change_type: str
    severity: ChangeSeverity
    before: Any
    after: Any


def diff_schemas(before: dict[str, Any], after: dict[str, Any]) -> list[StructuralChange]:
    """Classify top-level JSON Schema property changes into hard/soft/safe breaks.

    Args:
        before: Yesterday's ``input_schema`` (JSON Schema object).
        after: Today's ``input_schema``.

    Returns:
        List of :class:`StructuralChange` (empty if schemas are equivalent for
        the properties this walker understands).
    """
    changes: list[StructuralChange] = []
    before_props: dict[str, Any] = before.get("properties", {}) or {}
    after_props: dict[str, Any] = after.get("properties", {}) or {}
    before_required = set(before.get("required", []) or [])
    after_required = set(after.get("required", []) or [])

    for name in before_required - after_required:
        if name in after_props:
            changes.append(
                StructuralChange(
                    name, "required_to_optional", ChangeSeverity.SOFT_BREAK, True, False
                )
            )
        else:
            changes.append(
                StructuralChange(
                    name, "required_field_removed", ChangeSeverity.HARD_BREAK, name, None
                )
            )

    for name in after_required - before_required:
        changes.append(
            StructuralChange(name, "optional_to_required", ChangeSeverity.HARD_BREAK, False, True)
        )

    for name in before_props.keys() - after_props.keys() - before_required:
        changes.append(
            StructuralChange(name, "optional_field_removed", ChangeSeverity.SOFT_BREAK, name, None)
        )

    for name in after_props.keys() - before_props.keys():
        severity = ChangeSeverity.HARD_BREAK if name in after_required else ChangeSeverity.SAFE
        changes.append(StructuralChange(name, "field_added", severity, None, name))

    for name in before_props.keys() & after_props.keys():
        b, a = before_props[name], after_props[name]

        if b.get("type") != a.get("type"):
            changes.append(
                StructuralChange(
                    f"{name}.type",
                    "type_changed",
                    ChangeSeverity.HARD_BREAK,
                    b.get("type"),
                    a.get("type"),
                )
            )

        b_enum, a_enum = set(b.get("enum") or []), set(a.get("enum") or [])
        if b_enum and a_enum and a_enum < b_enum:
            changes.append(
                StructuralChange(
                    f"{name}.enum",
                    "enum_narrowed",
                    ChangeSeverity.SOFT_BREAK,
                    sorted(b_enum),
                    sorted(a_enum),
                )
            )
        elif b_enum and a_enum and a_enum > b_enum:
            changes.append(
                StructuralChange(
                    f"{name}.enum",
                    "enum_widened",
                    ChangeSeverity.SAFE,
                    sorted(b_enum),
                    sorted(a_enum),
                )
            )

        if b.get("default") != a.get("default"):
            changes.append(
                StructuralChange(
                    f"{name}.default",
                    "default_changed",
                    ChangeSeverity.SOFT_BREAK,
                    b.get("default"),
                    a.get("default"),
                )
            )

        for bound, direction in [("maximum", "lower"), ("minimum", "higher")]:
            if bound in b and bound in a and a[bound] != b[bound]:
                tightened = a[bound] < b[bound] if direction == "lower" else a[bound] > b[bound]
                if tightened:
                    changes.append(
                        StructuralChange(
                            f"{name}.{bound}",
                            f"{bound}_tightened",
                            ChangeSeverity.SOFT_BREAK,
                            b[bound],
                            a[bound],
                        )
                    )

    return changes


def worst_severity(changes: list[StructuralChange]) -> ChangeSeverity:
    """Collapse a list of changes to the single worst severity.

    Args:
        changes: Structural changes from :func:`diff_schemas`.

    Returns:
        ``HARD_BREAK`` if any hard break exists, else ``SOFT_BREAK``, else
        ``SAFE`` if anything changed, else ``NONE``.
    """
    if any(c.severity == ChangeSeverity.HARD_BREAK for c in changes):
        return ChangeSeverity.HARD_BREAK
    if any(c.severity == ChangeSeverity.SOFT_BREAK for c in changes):
        return ChangeSeverity.SOFT_BREAK
    if changes:
        return ChangeSeverity.SAFE
    return ChangeSeverity.NONE
