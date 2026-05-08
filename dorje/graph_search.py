"""Graph search — traversal and semantic search over the knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dorje.storage import PartitionStore
from dorje.types import GraphNode, Triple

_MAX_TRAVERSAL_DEPTH = 20
_MAX_RESULTS = 10_000


@dataclass(frozen=True, slots=True)
class GraphMatch:
    """A single graph search match."""

    node_id: str
    score: float
    path: tuple[str, ...]  # Traversal path from query to this node
    via_verb: str | None  # The verb that connected this result


def build_adjacency(
    triples: list[Triple],
) -> dict[str, list[tuple[str, str, str]]]:
    """Build adjacency list from triples.

    Returns dict mapping node_id -> list of (verb, target_id, triple_source).
    Bidirectional triples produce edges in both directions.
    """
    adj: dict[str, list[tuple[str, str, str]]] = {}

    max_triples = 500_000
    assert len(triples) <= max_triples, f"Too many triples ({len(triples)} > {max_triples})"

    for triple in triples:
        if triple.subject not in adj:
            adj[triple.subject] = []
        adj[triple.subject].append((triple.verb, triple.object, triple.source))

        if triple.bidirectional:
            if triple.object not in adj:
                adj[triple.object] = []
            adj[triple.object].append((triple.verb, triple.subject, triple.source))

    return adj


def traverse(
    start_id: str,
    adjacency: dict[str, list[tuple[str, str, str]]],
    max_depth: int = 3,
    verb_filter: frozenset[str] | None = None,
    source_filter: str | None = None,
) -> list[GraphMatch]:
    """BFS traversal from a starting node.

    Args:
        start_id: Node ID to start from.
        adjacency: Adjacency list from build_adjacency.
        max_depth: Maximum traversal depth.
        verb_filter: If set, only follow edges with these verbs.
        source_filter: If set, only follow edges from this source ("ast" or "llm").

    Returns:
        All reachable nodes with their traversal paths.
    """
    assert start_id, "start_id must not be empty"
    assert 0 < max_depth <= _MAX_TRAVERSAL_DEPTH, (
        f"max_depth must be in (0, {_MAX_TRAVERSAL_DEPTH}], got {max_depth}"
    )

    visited: set[str] = {start_id}
    results: list[GraphMatch] = []
    # Queue: (node_id, path, depth)
    queue: list[tuple[str, tuple[str, ...], int]] = [(start_id, (start_id,), 0)]

    head = 0
    max_iterations = _MAX_RESULTS

    for _ in range(max_iterations):
        if head >= len(queue):
            break

        current_id, path, depth = queue[head]
        head += 1

        if depth >= max_depth:
            continue

        neighbors = adjacency.get(current_id, [])

        for verb, target_id, source in neighbors:
            if target_id in visited:
                continue

            if verb_filter is not None and verb not in verb_filter:
                continue

            if source_filter is not None and source != source_filter:
                continue

            visited.add(target_id)
            new_path = path + (target_id,)

            # Score decays with depth: 1.0, 0.5, 0.33, 0.25, ...
            score = 1.0 / (depth + 1)

            results.append(GraphMatch(
                node_id=target_id,
                score=score,
                path=new_path,
                via_verb=verb,
            ))

            queue.append((target_id, new_path, depth + 1))

    return results


def semantic_verb_search(
    query_vector: np.ndarray,
    partition: PartitionStore,
    top_k: int,
    slab_size: int | None = None,
) -> list[tuple[str, float]]:
    """Find verbs semantically similar to a query.

    Returns list of (verb_text, similarity_score) sorted descending.
    """
    assert query_vector.ndim == 1, f"query must be 1D, got shape {query_vector.shape}"
    assert top_k > 0, f"top_k must be > 0, got {top_k}"

    query_norm = np.linalg.norm(query_vector)
    assert query_norm > 0, "query vector must not be zero"
    normalized_query = query_vector / query_norm

    results: list[tuple[str, float]] = []

    for ids, vectors in partition.read_graph_vectors("verb", slab_size):
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)
        normalized = vectors / norms
        scores = normalized @ normalized_query

        for i in range(len(ids)):
            results.append((ids[i], float(scores[i])))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def semantic_node_search(
    query_vector: np.ndarray,
    partition: PartitionStore,
    top_k: int,
    slab_size: int | None = None,
) -> list[GraphMatch]:
    """Find graph nodes semantically similar to a query.

    Returns list of GraphMatch sorted by descending score.
    """
    assert query_vector.ndim == 1, f"query must be 1D, got shape {query_vector.shape}"
    assert top_k > 0, f"top_k must be > 0, got {top_k}"

    query_norm = np.linalg.norm(query_vector)
    assert query_norm > 0, "query vector must not be zero"
    normalized_query = query_vector / query_norm

    results: list[GraphMatch] = []

    for ids, vectors in partition.read_graph_vectors("node", slab_size):
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)
        normalized = vectors / norms
        scores = normalized @ normalized_query

        for i in range(len(ids)):
            results.append(GraphMatch(
                node_id=ids[i],
                score=float(scores[i]),
                path=(ids[i],),
                via_verb=None,
            ))

    results.sort(key=lambda m: m.score, reverse=True)
    return results[:top_k]


def search_graph_across_partitions(
    query_vector: np.ndarray,
    partitions: list[PartitionStore],
    top_k: int,
    slab_size: int | None = None,
) -> list[GraphMatch]:
    """Search graph nodes across partitions."""
    assert top_k > 0

    all_matches: list[GraphMatch] = []
    for partition in partitions:
        matches = semantic_node_search(query_vector, partition, top_k, slab_size)
        all_matches.extend(matches)

    all_matches.sort(key=lambda m: m.score, reverse=True)
    return all_matches[:top_k]
