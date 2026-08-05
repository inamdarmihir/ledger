"""Heuristic snapshot cadence prioritization for MCP servers.

Not every MCP server deserves the same monitoring investment. Combine call
volume with whether the server sits on a customer-facing path to allocate how
often you are willing to hit someone else's server just to check for drift.

This is a starting heuristic, not a formula to defend rigorously — the point is
that snapshot cadence should be a deliberate allocation of a scarce resource.

Design article: Prioritizing Which Servers to Snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ServerPriority:
    """Priority metadata used to size snapshot cadence for one server.

    Attributes:
        server_name: MCP server label.
        call_volume_last_30d: How often agents invoked this server's tools.
        in_customer_facing_path: Whether a silent break is a production incident.
        snapshot_cadence_hours: Recommended hours between forced ``tools/list``
            snapshots (from :func:`recommend_cadence` or an override).
    """

    server_name: str
    call_volume_last_30d: int
    in_customer_facing_path: bool
    snapshot_cadence_hours: int


def recommend_cadence(volume: int, customer_facing: bool) -> int:
    """Return recommended snapshot cadence in hours.

    Args:
        volume: Call volume over the last ~30 days.
        customer_facing: Whether the server is on a customer-facing agent path.

    Returns:
        ``6`` (four times a day) for high-traffic customer-facing servers,
        ``24`` (daily) for either high-traffic or customer-facing,
        ``72`` (every three days) for low-traffic internal servers.
    """
    if customer_facing and volume > 1000:
        return 6
    if customer_facing or volume > 1000:
        return 24
    return 72
