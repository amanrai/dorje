"""Vector search — brute-force cosine similarity over numpy arrays."""

from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np

from dorje.storage import PartitionStore


@dataclass(frozen=True, slots=True)
class VectorMatch:
    """A single vector search match."""

    chunk_id: str
    score: float


def search_partition(
    query_vector: np.ndarray,
    partition: PartitionStore,
    kind: str,
    top_k: int,
    slab_size: int | None = None,
) -> list[VectorMatch]:
    """Search a single partition for nearest vectors.

    Args:
        query_vector: (dimension,) float32 query embedding.
        partition: Partition to search.
        kind: 'content' or 'metadata'.
        top_k: Number of results to return.
        slab_size: Slab size for memory-bounded loading. None = load all.

    Returns:
        Top-k matches sorted by descending score.
    """
    assert query_vector.ndim == 1, f"query must be 1D, got shape {query_vector.shape}"
    assert top_k > 0, f"top_k must be > 0, got {top_k}"
    assert kind in ("content", "metadata"), f"kind must be 'content' or 'metadata', got {kind}"

    # Normalize query once
    query_norm = np.linalg.norm(query_vector)
    assert query_norm > 0, "query vector must not be zero"
    normalized_query = query_vector / query_norm

    # Min-heap of (score, chunk_id) — we keep the top-k highest scores
    heap: list[tuple[float, str]] = []

    for ids, vectors in partition.read_vectors(kind, slab_size):
        assert vectors.ndim == 2, f"vectors must be 2D, got shape {vectors.shape}"
        assert vectors.shape[1] == query_vector.shape[0], (
            f"Dimension mismatch: vectors={vectors.shape[1]}, query={query_vector.shape[0]}"
        )

        # Batch cosine similarity: normalize rows, dot with query
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        # Avoid division by zero
        norms = np.maximum(norms, 1e-10)
        normalized = vectors / norms
        scores = normalized @ normalized_query  # (n,) array

        # Update top-k heap
        max_ids = len(ids)
        for i in range(max_ids):
            score = float(scores[i])
            if len(heap) < top_k:
                heapq.heappush(heap, (score, ids[i]))
            elif score > heap[0][0]:
                heapq.heapreplace(heap, (score, ids[i]))

    # Sort descending by score
    results = [VectorMatch(chunk_id=cid, score=s) for s, cid in heap]
    results.sort(key=lambda m: m.score, reverse=True)
    return results


def search_partitions(
    query_vector: np.ndarray,
    partitions: list[PartitionStore],
    kind: str,
    top_k: int,
    slab_size: int | None = None,
) -> list[VectorMatch]:
    """Search across multiple partitions and merge results."""
    assert top_k > 0, f"top_k must be > 0, got {top_k}"

    all_matches: list[VectorMatch] = []
    for partition in partitions:
        matches = search_partition(query_vector, partition, kind, top_k, slab_size)
        all_matches.extend(matches)

    # Re-sort and truncate
    all_matches.sort(key=lambda m: m.score, reverse=True)
    return all_matches[:top_k]
