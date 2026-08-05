"""Daily snapshots as append-only ground truth for MCP tool schemas.

Every tool on every MCP server your agents depend on gets one recorded snapshot
per day: its name, its description, and its full JSON Schema for arguments,
flattened into a single definition string for later embedding.

This is deliberately not fancy — an append-only structured log, not a database
with update semantics — because the entire point is to keep an immutable history
to diff against, not a single current-state row that would overwrite yesterday.

Design article: Component One — Daily Snapshots as Ground Truth.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ledger.protocols import MCPClientLike


@dataclass
class ToolSnapshot:
    """One recorded observation of a single tool on a single day.

    Attributes:
        server_name: Logical name of the MCP server (your key into the clients
            dict passed to :func:`snapshot_all_servers`).
        tool_name: Tool name as returned by ``tools/list``.
        snapshot_date: ISO date string (``YYYY-MM-DD``). One snapshot per tool
            per day is the intended cadence; tighter cadences may reuse the
            same field with a finer grain if you prefer.
        description: Tool description text at snapshot time.
        input_schema: JSON Schema for the tool's arguments.
        raw_definition: ``name + description + schema`` flattened for embedding
            into Qdrant (see :class:`ledger.semantic.ToolDefinitionHistory`).
    """

    server_name: str
    tool_name: str
    snapshot_date: str
    description: str
    input_schema: dict[str, Any]
    raw_definition: str


def build_snapshot(
    server_name: str,
    tool_name: str,
    description: str,
    input_schema: dict[str, Any],
    snapshot_date: str,
) -> ToolSnapshot:
    """Build a :class:`ToolSnapshot` with a deterministic ``raw_definition``.

    The raw definition sorts schema keys so semantically identical schemas
    produce identical embedding text regardless of key order from the wire.

    Args:
        server_name: Consumer-side label for the MCP server.
        tool_name: Tool name from ``tools/list``.
        description: Tool description from ``tools/list``.
        input_schema: JSON Schema object for arguments.
        snapshot_date: ISO date for this observation.

    Returns:
        A fully populated :class:`ToolSnapshot`.
    """
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
    """Append-only JSONL log — raw ground truth the rest of the pipeline uses.

    Nothing here talks to Qdrant or embeddings. This store is plain durable
    history so the structural differ and semantic layer can run offline later.
    """

    def __init__(self, path: str) -> None:
        """Create a store backed by ``path`` (created on first :meth:`append`).

        Args:
            path: Filesystem path to the JSONL log (e.g. ``tool_snapshots.jsonl``).
        """
        self.path = path

    def append(self, snapshot: ToolSnapshot) -> None:
        """Append one snapshot as a single JSON line.

        Args:
            snapshot: Observation to persist.
        """
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(snapshot)) + "\n")

    def load_history(self, server_name: str, tool_name: str) -> list[ToolSnapshot]:
        """Load all snapshots for one tool, oldest first.

        Args:
            server_name: Server label used when the snapshot was written.
            tool_name: Tool name to filter on.

        Returns:
            Sorted list of matching snapshots (empty if the file is missing).
        """
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
        """Return ``(today, yesterday)`` for the structural diff.

        Either may be ``None`` on the first day a tool is observed.

        Args:
            server_name: Server label.
            tool_name: Tool name.

        Returns:
            Tuple of (most recent snapshot, previous snapshot).
        """
        history = self.load_history(server_name, tool_name)
        if not history:
            return None, None
        if len(history) == 1:
            return history[-1], None
        return history[-1], history[-2]

    def known_tools(self) -> list[tuple[str, str]]:
        """Return unique ``(server_name, tool_name)`` pairs in first-seen order.

        Returns:
            Ordered list of tool keys present in the log.
        """
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
    """Force a live ``tools/list`` against every server and append snapshots.

    Each client's ``list_tools`` is called with ``force_refresh=True``: the
    monitoring cadence is independent of the client's own tools/list cache TTL.
    A caching-aware client used for live traffic is exactly the thing we do
    **not** want to trust here.

    Args:
        clients: Map of ``server_name -> MCPClientLike``.
        store: Append-only snapshot log.
        snapshot_date: ISO date stamped onto every snapshot from this run.

    Returns:
        The list of snapshots just written (also persisted to ``store``).
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
