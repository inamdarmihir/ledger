"""Snapshot store and snapshot_all_servers tests."""

from __future__ import annotations

from pathlib import Path

from ledger.protocols import ListToolsResult, ToolInfo
from ledger.snapshot import SnapshotStore, build_snapshot, snapshot_all_servers


class _Client:
    def __init__(self) -> None:
        self.force_refresh_seen = False

    def list_tools(self, *, force_refresh: bool = False) -> ListToolsResult:
        self.force_refresh_seen = force_refresh
        return ListToolsResult(
            tools=[
                ToolInfo(
                    name="search_customers",
                    description="Search customers",
                    input_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                )
            ]
        )


def test_build_snapshot_flattens_raw_definition() -> None:
    snap = build_snapshot(
        server_name="crm",
        tool_name="search_customers",
        description="Search customer records by name or account ID.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        snapshot_date="2026-07-15",
    )
    assert snap.tool_name in snap.raw_definition
    assert "Search customer records" in snap.raw_definition
    assert '"query"' in snap.raw_definition


def test_snapshot_store_append_and_latest_pair(tmp_path: Path) -> None:
    store = SnapshotStore(str(tmp_path / "tool_snapshots.jsonl"))
    a = build_snapshot("crm", "search_customers", "d1", {"type": "object"}, "2026-07-15")
    b = build_snapshot("crm", "search_customers", "d2", {"type": "object"}, "2026-07-16")
    store.append(a)
    today, yesterday = store.latest_pair("crm", "search_customers")
    assert today is not None and yesterday is None
    store.append(b)
    today, yesterday = store.latest_pair("crm", "search_customers")
    assert today is not None and yesterday is not None
    assert today.snapshot_date == "2026-07-16"
    assert yesterday.snapshot_date == "2026-07-15"


def test_snapshot_all_servers_force_refresh(tmp_path: Path) -> None:
    client = _Client()
    store = SnapshotStore(str(tmp_path / "tool_snapshots.jsonl"))
    snaps = snapshot_all_servers({"crm": client}, store, "2026-07-15")
    assert client.force_refresh_seen is True
    assert len(snaps) == 1
    assert snaps[0].server_name == "crm"
    assert store.known_tools() == [("crm", "search_customers")]
