"""Qdrant-backed semantic drift detection over tool definition embeddings."""

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

# text-embedding-3-small default output size (OpenAI, verified 2026).
DEFAULT_VECTOR_SIZE = 1536


def _is_local_qdrant(client: QdrantClient) -> bool:
    inner = getattr(client, "_client", None)
    return inner is not None and "qdrant_local" in type(inner).__module__


class ToolDefinitionHistory:
    """Embeddings of each tool's definition text over time (not the raw snapshots).

    Answers: does today's definition read like a continuation of this tool's
    own history, or a departure from it?
    """

    def __init__(
        self,
        client: QdrantClient,
        embed_fn: EmbedFn,
        collection: str = "tool_definition_history",
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ) -> None:
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
        """Compare today's definition against this tool's own historical embeddings."""
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
