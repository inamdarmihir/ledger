"""Priority heuristics and CLI smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

from ledger.cli import main
from ledger.priority import recommend_cadence


def test_recommend_cadence_matrix() -> None:
    assert recommend_cadence(5000, True) == 6
    assert recommend_cadence(500, True) == 24
    assert recommend_cadence(5000, False) == 24
    assert recommend_cadence(10, False) == 72


def test_cli_diff_pair(tmp_path: Path, capsys) -> None:
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
    b = tmp_path / "before.json"
    a = tmp_path / "after.json"
    b.write_text(json.dumps(before), encoding="utf-8")
    a.write_text(json.dumps(after), encoding="utf-8")
    try:
        main(["diff-pair", str(b), str(a)])
    except SystemExit as exc:
        assert exc.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["severity"] == "soft_break"
    assert out["changes"][0]["change_type"] == "default_changed"
