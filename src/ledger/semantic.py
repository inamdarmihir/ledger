"""Qdrant-backed semantic drift detection over tool definition embeddings.

The structural differ has nothing to say about a description rewrite that leaves
the schema shape untouched. That is the gap this module fills: each tool's full
definition text — name, description, and parameter documentation — gets embedded
and stored, and every new snapshot is compared against that tool's *own*
prior-snapshot embedding history (filtered to the exact ``server_name`` +
``tool_name`` pair).

A large semantic distance from a tool's own established trajectory, even with an
identical JSON Schema, is the signal that a rewording may be shifting what the
model infers about correct usage.

Uses Qdrant's current Query API (``query_points`` + ``PointStruct``). Default
vector size is **1536**, matching OpenAI ``text-embedding-3-small``.

Design article: Component Three — Qdrant as the Semantic-Drift Side-Piece.
"""

from __future__ import annotations

import uuid
import warnings
from collections.abc import Callable
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from ledger.snapshot import ToolSnapshot

EmbedFn = Callable[[str], list[float]]

# text-embedding-3-small default output size (OpenAI, verified against docs).
DEFAULT_VECTOR_SIZE = 1536


def _is_local_qdrant(client: QdrantClient) -> bool:
    """Return True when the client is in-process local / ``:memory:`` mode."""
    inner = getattr(client, "_client", None)
    return inner is not None and "qdrant_local" in type(inner).__module__


class ToolDefinitionHistory:
    """Embeddings of each tool's definition text over time.

    Qdrant holds vectors — not the raw snapshots themselves (those live in
    :class:`~ledger.snapshot.SnapshotStore`). This collection answers one
    question: does today's definition read like a continuation of this tool's
    own history, or a departure from it?
    """

    def __init__(
        self,
        client: QdrantClient,
        embed_fn: EmbedFn,
        collection: str = "tool_definition_history",
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ) -> None:
        """Ensure the collection exists and store the embedding callable.

        Args:
            client: Qdrant client (server URL or ``location=":memory:"`` for
                offline demos / tests).
            embed_fn: ``Callable[[str], list[float]]`` — typically
                :func:`ledger.embeddings.make_openai_embed_fn` in production.
            collection: Qdrant collection name.
            vector_size: Expected embedding dimensionality (must match
                ``embed_fn`` output; default 1536 for ``text-embedding-3-small``).
        """
        self.client = client
        self.embed_fn = embed_fn
        self.collection = collection
        self.vector_size = vector_size
        existing = {c.name for c in client.get_collections().collections}
        if collection not in existing:
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            # Indexes help server-side filtered search; local/:memory: mode ignores them.
            if not _is_local_qdrant(client):
                for field_name, schema in [
                    ("server_name", PayloadSchemaType.KEYWORD),
                    ("tool_name", PayloadSchemaType.KEYWORD),
                    ("snapshot_date", PayloadSchemaType.KEYWORD),
                ]:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        client.create_payload_index(
                            collection_name=collection,
                            field_name=field_name,
                            field_schema=schema,
                        )

    def record(self, snapshot: ToolSnapshot) -> None:
        """Upsert today's definition embedding into the per-tool history.

        Args:
            snapshot: Snapshot whose ``raw_definition`` will be embedded.

        Raises:
            ValueError: If ``embed_fn`` returns the wrong dimensionality.
        """
        vector = self.embed_fn(snapshot.raw_definition)
        if len(vector) != self.vector_size:
            raise ValueError(
                f"embed_fn returned {len(vector)} dims; collection expects {self.vector_size}"
            )
        self.client.upsert(
            collection_name=self.collection,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "server_name": snapshot.server_name,
                        "tool_name": snapshot.tool_name,
                        "snapshot_date": snapshot.snapshot_date,
                        "raw_definition": snapshot.raw_definition,
                    },
                )
            ],
        )

    def check_drift(
        self,
        snapshot: ToolSnapshot,
        top_k: int = 14,
        similarity_floor: float = 0.90,
    ) -> dict[str, Any]:
        """Compare today's definition against this tool's own historical embeddings.

        The filter pins both ``server_name`` and ``tool_name`` — drifting relative
        to a *different* tool's history would be meaningless.

        Args:
            snapshot: Today's snapshot to evaluate.
            top_k: How many prior embeddings to average over.
            similarity_floor: Mean cosine similarity below which we flag drift.
                ``0.90`` is an illustrative starting point (see article Challenges).

        Returns:
            Dict with ``drifted``, ``reason``, ``mean_similarity``, and when
            history exists, the most similar prior date/text for human review.
        """
        hits = self.client.query_points(
            collection_name=self.collection,
            query=self.embed_fn(snapshot.raw_definition),
            query_filter=Filter(
                must=[
                    FieldCondition(key="server_name", match=MatchValue(value=snapshot.server_name)),
                    FieldCondition(key="tool_name", match=MatchValue(value=snapshot.tool_name)),
                ]
            ),
            limit=top_k,
            with_payload=True,
        ).points

        if not hits:
            return {"drifted": False, "reason": "no_history_yet", "mean_similarity": None}

        mean_similarity = sum(h.score for h in hits) / len(hits)
        drifted = mean_similarity < similarity_floor
        first = hits[0]
        payload = first.payload or {}
        return {
            "drifted": drifted,
            "reason": "semantic_drift" if drifted else "stable",
            "mean_similarity": mean_similarity,
            "most_similar_prior_date": payload.get("snapshot_date"),
            "most_similar_prior_text": payload.get("raw_definition"),
        }
