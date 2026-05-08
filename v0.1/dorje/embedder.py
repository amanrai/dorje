"""Embedding client — talks to any OpenAI-compatible /v1/embeddings endpoint."""

from __future__ import annotations

import numpy as np
from openai import OpenAI

from dorje.config import EmbedderConfig

_MAX_BATCH_SIZE = 2048  # Hard upper bound regardless of config


class Embedder:
    """Embedding client using OpenAI-compatible API."""

    def __init__(self, config: EmbedderConfig) -> None:
        config.validate()
        self._config = config
        self._client = OpenAI(
            base_url=config.endpoint,
            api_key=config.auth_key or "unused",
        )
        self._dimension = config.dimension
        self._batch_size = min(config.batch_size, _MAX_BATCH_SIZE)

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts. Returns (n, dimension) float32 array.

        Handles batching internally. Empty input returns empty array.
        """
        assert isinstance(texts, list), f"texts must be a list, got {type(texts).__name__}"

        if not texts:
            return np.zeros((0, self._dimension), dtype=np.float32)

        all_vectors: list[list[float]] = []
        total = len(texts)
        offset = 0
        max_iterations = (total // self._batch_size) + 2  # Safety bound

        for _ in range(max_iterations):
            if offset >= total:
                break

            end = min(offset + self._batch_size, total)
            batch = texts[offset:end]

            assert all(isinstance(t, str) for t in batch), "all texts must be strings"
            assert all(len(t) > 0 for t in batch), "all texts must be non-empty"

            response = self._client.embeddings.create(
                model=self._config.model,
                input=batch,
            )

            assert len(response.data) == len(batch), (
                f"Expected {len(batch)} embeddings, got {len(response.data)}"
            )

            for item in response.data:
                vec = item.embedding
                assert len(vec) == self._dimension, (
                    f"Expected dimension {self._dimension}, got {len(vec)}"
                )
                all_vectors.append(vec)

            offset = end

        assert len(all_vectors) == total, (
            f"Expected {total} vectors, got {len(all_vectors)}"
        )

        return np.array(all_vectors, dtype=np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text. Returns (dimension,) float32 array."""
        assert isinstance(text, str), f"text must be a string, got {type(text).__name__}"
        assert len(text) > 0, "text must be non-empty"

        result = self.embed([text])
        return result[0]

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        return self._dimension
