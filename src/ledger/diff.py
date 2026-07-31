"""Deterministic structural JSON-Schema diff for MCP tool input schemas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ChangeSeverity(StrEnum):
    HARD_BREAK = "hard_break"  # previously-valid calls will now fail outright
    SOFT_BREAK = "soft_break"  # some previously-valid calls may now fail or behave differently
    SAFE = "safe"  # additive, does not invalidate prior calls
    NONE = "none"


@dataclass
class StructuralChange:
    field_path: str
    change_type: str
    severity: ChangeSeverity
    before: Any
    after: Any


def diff_schemas(before: dict[str, Any], after: dict[str, Any]) -> list[StructuralChange]:
    """Classify top-level JSON Schema property changes into hard/soft/safe breaks."""
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
    if any(c.severity == ChangeSeverity.HARD_BREAK for c in changes):
        return ChangeSeverity.HARD_BREAK
    if any(c.severity == ChangeSeverity.SOFT_BREAK for c in changes):
        return ChangeSeverity.SOFT_BREAK
    if changes:
        return ChangeSeverity.SAFE
    return ChangeSeverity.NONE
