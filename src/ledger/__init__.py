"""Ledger: consumer-side contract guard for MCP tool-schema drift.

Ledger watches Model Context Protocol servers you *consume but do not control*.
It takes an independent daily ``tools/list`` snapshot (bypassing client-side
cache TTLs), diffs each tool's JSON Schema structurally, and checks description
rewrites for semantic drift in Qdrant. Findings go to a human review queue —
never an automated block.

This package is the end-to-end implementation of the design in
``docs/article.md``. For install and Agents SDK wiring, see the project README
and ``docs/SETUP.md``.

Quick start::

    from ledger import (
        SnapshotStore,
        ToolDefinitionHistory,
        snapshot_all_servers,
        run_contract_guard,
        route_report,
        format_for_digest,
    )

Public API surface matches the components described in the design article
(snapshots, structural diff, semantic history, reports, routing, cadence).
"""

from ledger.diff import ChangeSeverity, StructuralChange, diff_schemas, worst_severity
from ledger.priority import ServerPriority, recommend_cadence
from ledger.protocols import ListToolsResult, MCPClientLike, ToolInfo
from ledger.report import DriftReport, run_contract_guard
from ledger.routing import format_for_digest, route_report
from ledger.semantic import DEFAULT_VECTOR_SIZE, ToolDefinitionHistory
from ledger.snapshot import SnapshotStore, ToolSnapshot, build_snapshot, snapshot_all_servers

__all__ = [
    "DEFAULT_VECTOR_SIZE",
    "ChangeSeverity",
    "DriftReport",
    "ListToolsResult",
    "MCPClientLike",
    "ServerPriority",
    "SnapshotStore",
    "StructuralChange",
    "ToolDefinitionHistory",
    "ToolInfo",
    "ToolSnapshot",
    "build_snapshot",
    "diff_schemas",
    "format_for_digest",
    "recommend_cadence",
    "route_report",
    "run_contract_guard",
    "snapshot_all_servers",
    "worst_severity",
]

__version__ = "0.1.0"
