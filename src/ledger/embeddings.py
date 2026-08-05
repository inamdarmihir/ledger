"""OpenAI embedding helpers for :class:`~ledger.semantic.ToolDefinitionHistory`.

Verified against OpenAI embeddings docs: ``text-embedding-3-small`` defaults to
**1536** dimensions, matching Ledger's Qdrant collection size
(:data:`~ledger.semantic.DEFAULT_VECTOR_SIZE`).

Install the optional extra before using this module::

    pip install -e ".[openai]"

Then::

    from openai import OpenAI
    from ledger.embeddings import make_openai_embed_fn

    embed_fn = make_openai_embed_fn(OpenAI())  # needs OPENAI_API_KEY
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
    """Return an ``embed_fn(text) -> list[float]`` for ToolDefinitionHistory.

    Args:
        client: Configured :class:`openai.OpenAI` client.
        model: Embedding model id (default ``text-embedding-3-small``).
        dimensions: Output dimensionality — must match the Qdrant collection
            ``vector_size`` (default 1536).

    Returns:
        A callable suitable for the ``embed_fn`` argument of
        :class:`~ledger.semantic.ToolDefinitionHistory`.
    """

    def embed_fn(text: str) -> list[float]:
        response = client.embeddings.create(
            model=model,
            input=text,
            dimensions=dimensions,
        )
        return list(response.data[0].embedding)

    return embed_fn
