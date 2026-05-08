"""Search orchestrator — fuses vector, BM25, and graph search results."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, Future
from dataclasses import dataclass

import numpy as np

from dorje.bm25_search import BM25Match, search_bm25_across_partitions
from dorje.config import Config
from dorje.embedder import Embedder
from dorje.graph_search import GraphMatch, search_graph_across_partitions
from dorje.storage import IndexStore, PartitionStore
from dorje.types import Chunk, SearchResult
from dorje.vector_search import VectorMatch, search_partitions

_DEFAULT_CONTENT_WEIGHT = 0.35
_DEFAULT_METADATA_WEIGHT = 0.25
_DEFAULT_BM25_WEIGHT = 0.25
_DEFAULT_GRAPH_WEIGHT = 0.15


@dataclass(frozen=True, slots=True)
class SearchWeights:
    """Weights for fusing search modalities."""

    content_vector: float = _DEFAULT_CONTENT_WEIGHT
    metadata_vector: float = _DEFAULT_METADATA_WEIGHT
    bm25: float = _DEFAULT_BM25_WEIGHT
    graph: float = _DEFAULT_GRAPH_WEIGHT

    def validate(self) -> None:
        """Validate weights are positive."""
        assert self.content_vector >= 0, f"content_vector weight must be >= 0"
        assert self.metadata_vector >= 0, f"metadata_vector weight must be >= 0"
        assert self.bm25 >= 0, f"bm25 weight must be >= 0"
        assert self.graph >= 0, f"graph weight must be >= 0"
        total = self.content_vector + self.metadata_vector + self.bm25 + self.graph
        assert total > 0, "At least one weight must be > 0"


def search(
    query: str,
    index: IndexStore,
    embedder: Embedder,
    config: Config,
    weights: SearchWeights | None = None,
) -> list[SearchResult]:
    """Execute a search across all modalities.

    Args:
        query: The search query string.
        index: The index to search.
        embedder: Embedder for query vectorization.
        config: Dorje configuration.
        weights: Optional custom weights. Defaults to balanced weights.

    Returns:
        Ranked list of SearchResult, up to config.search.top_k.
    """
    assert query, "query must not be empty"

    if weights is None:
        weights = SearchWeights()
    weights.validate()

    top_k = config.search.top_k
    slab_size = config.search.slab_size
    partitions = index.all_partitions()

    if not partitions:
        return []

    # Embed query
    query_vector = embedder.embed_single(query)

    # Run all search modalities
    # Fetch more candidates than top_k for better fusion
    fetch_k = top_k * 3

    content_matches = _search_content_vectors(
        query_vector, partitions, fetch_k, slab_size
    )
    metadata_matches = _search_metadata_vectors(
        query_vector, partitions, fetch_k, slab_size
    )
    bm25_matches = search_bm25_across_partitions(query, partitions, fetch_k)
    graph_matches = search_graph_across_partitions(
        query_vector, partitions, fetch_k, slab_size
    )

    # Build chunk lookups
    chunk_map, unit_to_chunks = _build_chunk_map(partitions)

    # Fuse scores
    fused = _fuse_results(
        content_matches=content_matches,
        metadata_matches=metadata_matches,
        bm25_matches=bm25_matches,
        graph_matches=graph_matches,
        weights=weights,
        chunk_map=chunk_map,
        unit_to_chunks=unit_to_chunks,
    )

    # Sort and truncate
    fused.sort(key=lambda r: r.score, reverse=True)
    return fused[:top_k]


def _search_content_vectors(
    query_vector: np.ndarray,
    partitions: list[PartitionStore],
    top_k: int,
    slab_size: int | None,
) -> list[VectorMatch]:
    """Search content vectors across partitions."""
    return search_partitions(query_vector, partitions, "content", top_k, slab_size)


def _search_metadata_vectors(
    query_vector: np.ndarray,
    partitions: list[PartitionStore],
    top_k: int,
    slab_size: int | None,
) -> list[VectorMatch]:
    """Search metadata vectors across partitions."""
    return search_partitions(query_vector, partitions, "metadata", top_k, slab_size)


def _build_chunk_map(
    partitions: list[PartitionStore],
) -> tuple[dict[str, Chunk], dict[str, list[Chunk]]]:
    """Build lookup tables from all partitions.

    Returns:
        chunk_map: chunk_id -> Chunk
        unit_to_chunks: unit_id (qualified_name) -> list of Chunks
    """
    chunk_map: dict[str, Chunk] = {}
    unit_to_chunks: dict[str, list[Chunk]] = {}
    for partition in partitions:
        chunks = partition.read_chunks()
        for chunk in chunks:
            chunk_map[chunk.id] = chunk
            if chunk.unit_id:
                if chunk.unit_id not in unit_to_chunks:
                    unit_to_chunks[chunk.unit_id] = []
                unit_to_chunks[chunk.unit_id].append(chunk)
    return chunk_map, unit_to_chunks


def _normalize_scores(matches: list[tuple[str, float]]) -> dict[str, float]:
    """Min-max normalize scores to [0, 1]."""
    if not matches:
        return {}

    scores = [s for _, s in matches]
    min_score = min(scores)
    max_score = max(scores)
    score_range = max_score - min_score

    result: dict[str, float] = {}
    for chunk_id, score in matches:
        if score_range > 0:
            result[chunk_id] = (score - min_score) / score_range
        else:
            result[chunk_id] = 1.0

    return result


def _fuse_results(
    content_matches: list[VectorMatch],
    metadata_matches: list[VectorMatch],
    bm25_matches: list[BM25Match],
    graph_matches: list[GraphMatch],
    weights: SearchWeights,
    chunk_map: dict[str, Chunk],
    unit_to_chunks: dict[str, list[Chunk]],
) -> list[SearchResult]:
    """Fuse results from all modalities into a single ranked list.

    Graph matches resolve via unit_to_chunks: a graph node_id (qualified_name)
    maps to all chunks belonging to that semantic unit.
    """
    # Normalize scores per modality
    content_scores = _normalize_scores(
        [(m.chunk_id, m.score) for m in content_matches]
    )
    metadata_scores = _normalize_scores(
        [(m.chunk_id, m.score) for m in metadata_matches]
    )
    bm25_scores = _normalize_scores(
        [(m.chunk_id, m.score) for m in bm25_matches]
    )

    # Graph scores: node_id → score. Resolve to chunk IDs via unit_to_chunks.
    raw_graph_scores = _normalize_scores(
        [(m.node_id, m.score) for m in graph_matches]
    )
    graph_scores: dict[str, float] = {}
    for node_id, score in raw_graph_scores.items():
        unit_chunks = unit_to_chunks.get(node_id, [])
        for uc in unit_chunks:
            # Keep highest graph score per chunk
            if uc.id not in graph_scores or score > graph_scores[uc.id]:
                graph_scores[uc.id] = score

    # Collect all candidate chunk IDs
    all_ids: set[str] = set()
    all_ids.update(content_scores.keys())
    all_ids.update(metadata_scores.keys())
    all_ids.update(bm25_scores.keys())
    all_ids.update(graph_scores.keys())

    # Compute fused score
    weight_sum = (
        weights.content_vector + weights.metadata_vector
        + weights.bm25 + weights.graph
    )
    assert weight_sum > 0

    results: list[SearchResult] = []
    for chunk_id in all_ids:
        chunk = chunk_map.get(chunk_id)
        if chunk is None:
            continue

        fused_score = (
            weights.content_vector * content_scores.get(chunk_id, 0.0)
            + weights.metadata_vector * metadata_scores.get(chunk_id, 0.0)
            + weights.bm25 * bm25_scores.get(chunk_id, 0.0)
            + weights.graph * graph_scores.get(chunk_id, 0.0)
        ) / weight_sum

        # Determine primary source
        source_scores = {
            "vector": content_scores.get(chunk_id, 0.0),
            "metadata": metadata_scores.get(chunk_id, 0.0),
            "bm25": bm25_scores.get(chunk_id, 0.0),
            "graph": graph_scores.get(chunk_id, 0.0),
        }
        primary_source = max(source_scores, key=lambda k: source_scores[k])

        results.append(SearchResult(
            chunk=chunk,
            score=fused_score,
            source=primary_source,
            highlights=(),  # TODO: extract relevant snippets
        ))

    return results
