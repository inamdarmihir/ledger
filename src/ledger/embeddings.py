"""OpenAI embedding helpers for ToolDefinitionHistory.

Verified against OpenAI embeddings docs (2026): ``text-embedding-3-small``
defaults to 1536 dimensions, matching Ledger's Qdrant collection size.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ledger.semantic import DEFAULT_VECTOR_SIZE

if TYPE_CHECKING:
    from openai import OpenAI

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def make_openai_embed_fn(
    client: OpenAI,
    *,
    model: str = DEFAULT_EMBEDDING_MODEL,
    dimensions: int = DEFAULT_VECTOR_SIZE,
) -> Callable[[str], list[float]]:
    """Return an ``embed_fn(text) -> list[float]`` compatible with ToolDefinitionHistory."""

    def embed_fn(text: str) -> list[float]:
        response = client.embeddings.create(
            model=model,
            input=text,
            dimensions=dimensions,
        )
        return list(response.data[0].embedding)

    return embed_fn
