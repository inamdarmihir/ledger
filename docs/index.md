# ledger

> MCP tool schema drift detector — know when an upstream server silently changes its contract.

__omp_shell("!! warning "Silent contract breakage"")
    An MCP server that removes a required parameter without a version bump will silently break every consumer agent at next restart. ledger catches it the day it happens.

## What it does

- Daily snapshots of `tools/list` from each MCP server (JSONL store)
- Structural JSON Schema diff: hard_break / soft_break / safe / none
- Semantic description drift via Qdrant embedding history
- Routes findings: page immediately / daily digest / log only
- mem0 cross-run drift pattern memory
- Agno triage agent generates GPT summaries for the digest queue
- LangGraph pipeline: detect → route → notify

## Why structural + semantic?

Structural diff catches breaking changes to parameter names and types.
Semantic diff catches description rewrites that change what the tool does without changing its signature — equally dangerous for agents that rely on descriptions to decide when to use a tool.

See [Quick Start](quickstart.md) to take your first snapshot.
