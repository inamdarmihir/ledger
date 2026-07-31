"""Structural diff tests aligned with the article taxonomy."""

from __future__ import annotations

from ledger.diff import ChangeSeverity, diff_schemas, worst_severity


def test_required_field_removed_is_hard_break() -> None:
    before = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query"],
    }
    after = {
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
        "required": [],
    }
    changes = diff_schemas(before, after)
    assert any(c.change_type == "required_field_removed" for c in changes)
    assert worst_severity(changes) == ChangeSeverity.HARD_BREAK


def test_optional_to_required_is_hard_break() -> None:
    before = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "region": {"type": "string"}},
        "required": ["query"],
    }
    after = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "region": {"type": "string"}},
        "required": ["query", "region"],
    }
    changes = diff_schemas(before, after)
    assert any(c.change_type == "optional_to_required" for c in changes)
    assert worst_severity(changes) == ChangeSeverity.HARD_BREAK


def test_enum_narrowed_is_soft_break() -> None:
    before = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["open", "pending", "closed", "archived"]}
        },
    }
    after = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["open", "closed"]}},
    }
    changes = diff_schemas(before, after)
    assert changes[0].change_type == "enum_narrowed"
    assert changes[0].severity == ChangeSeverity.SOFT_BREAK


def test_enum_widened_is_safe() -> None:
    before = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["open", "closed"]}},
    }
    after = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["open", "closed", "archived"]}},
    }
    changes = diff_schemas(before, after)
    assert changes[0].change_type == "enum_widened"
    assert worst_severity(changes) == ChangeSeverity.SAFE


def test_default_changed_is_soft_break_worked_example() -> None:
    before = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 20, "maximum": 100},
        },
        "required": ["query"],
    }
    after = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5, "maximum": 100},
        },
        "required": ["query"],
    }
    changes = diff_schemas(before, after)
    assert len(changes) == 1
    assert changes[0].field_path == "limit.default"
    assert changes[0].change_type == "default_changed"
    assert changes[0].severity == ChangeSeverity.SOFT_BREAK
    assert changes[0].before == 20
    assert changes[0].after == 5


def test_optional_field_added_is_safe() -> None:
    before = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    after = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "region": {"type": "string"},
        },
        "required": ["query"],
    }
    changes = diff_schemas(before, after)
    assert changes[0].change_type == "field_added"
    assert changes[0].severity == ChangeSeverity.SAFE


def test_maximum_tightened_is_soft_break() -> None:
    before = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "maximum": 100}},
    }
    after = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "maximum": 50}},
    }
    changes = diff_schemas(before, after)
    assert changes[0].change_type == "maximum_tightened"
    assert changes[0].severity == ChangeSeverity.SOFT_BREAK


def test_type_changed_is_hard_break() -> None:
    before = {"type": "object", "properties": {"limit": {"type": "integer"}}}
    after = {"type": "object", "properties": {"limit": {"type": "string"}}}
    changes = diff_schemas(before, after)
    assert changes[0].change_type == "type_changed"
    assert worst_severity(changes) == ChangeSeverity.HARD_BREAK


def test_identical_schemas_yield_none() -> None:
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    assert diff_schemas(schema, schema) == []
    assert worst_severity([]) == ChangeSeverity.NONE
