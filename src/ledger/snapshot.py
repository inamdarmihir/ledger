"""Daily snapshots as append-only ground truth for MCP tool schemas."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ledger.protocols import MCPClientLike


@dataclass
class ToolSnapshot:
    server_name: str
    tool_name: str
    snapshot_date: str  # ISO date, one snapshot per tool per day
    description: str
    input_schema: dict[str, Any]
    raw_definition: str  # name + description + schema, flattened for embedding


def build_snapshot(
    server_name: str,
    tool_name: str,
    description: str,
    input_schema: dict[str, Any],
    snapshot_date: str,
) -> ToolSnapshot:
    raw_definition = f"{tool_name}\n\n{description}\n\n{json.dumps(input_schema, sort_keys=True)}"
    return ToolSnapshot(
        server_name=server_name,
        tool_name=tool_name,
        snapshot_date=snapshot_date,
        description=description,
        input_schema=input_schema,
        raw_definition=raw_definition,
    )


class SnapshotStore:
    """Append-only JSONL log. Raw ground truth the rest of the pipeline reasons over."""

    def __init__(self, path: str) -> None:
        self.path = path

    def append(self, snapshot: ToolSnapshot) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(snapshot)) + "\n")

    def load_history(self, server_name: str, tool_name: str) -> list[ToolSnapshot]:
        history: list[ToolSnapshot] = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if row["server_name"] == server_name and row["tool_name"] == tool_name:
                        history.append(ToolSnapshot(**row))
        except FileNotFoundError:
            return []
        return sorted(history, key=lambda s: s.snapshot_date)

    def latest_pair(
        self, server_name: str, tool_name: str
    ) -> tuple[ToolSnapshot | None, ToolSnapshot | None]:
        """Returns (today, yesterday) for the structural diff.

        Either may be None on the first day a tool is observed.
        """
        history = self.load_history(server_name, tool_name)
        if not history:
            return None, None
        if len(history) == 1:
            return history[-1], None
        return history[-1], history[-2]

    def known_tools(self) -> list[tuple[str, str]]:
        """Return unique (server_name, tool_name) pairs seen in the log."""
        seen: set[tuple[str, str]] = set()
        ordered: list[tuple[str, str]] = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    key = (row["server_name"], row["tool_name"])
                    if key not in seen:
                        seen.add(key)
                        ordered.append(key)
        except FileNotFoundError:
            return []
        return ordered


def snapshot_all_servers(
    clients: dict[str, MCPClientLike],
    store: SnapshotStore,
    snapshot_date: str,
) -> list[ToolSnapshot]:
    """Force a live tools/list against every server and append snapshots.

    Each client's ``list_tools`` is called with ``force_refresh=True``: the
    monitoring cadence is independent of the client's own tools/list cache TTL.
    """
    snapshots: list[ToolSnapshot] = []
    for server_name, client in clients.items():
        result = client.list_tools(force_refresh=True)
        for tool in result.tools:
            snap = build_snapshot(
                server_name=server_name,
                tool_name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                snapshot_date=snapshot_date,
            )
            store.append(snap)
            snapshots.append(snap)
    return snapshots
