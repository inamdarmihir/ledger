"""Heuristic snapshot cadence prioritization for MCP servers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ServerPriority:
    server_name: str
    call_volume_last_30d: int
    in_customer_facing_path: bool
    snapshot_cadence_hours: int


def recommend_cadence(volume: int, customer_facing: bool) -> int:
    """Return recommended snapshot cadence in hours."""
    if customer_facing and volume > 1000:
        return 6  # four snapshots a day for high-traffic, high-stakes servers
    if customer_facing or volume > 1000:
        return 24  # daily for anything either high-traffic or customer-facing
    return 72  # every three days for low-traffic internal servers
