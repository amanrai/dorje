"""BM25 keyword search over chunk content."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from dorje.storage import PartitionStore
from dorje.types import Chunk

_MAX_CORPUS_SIZE = 1_000_000  # Safety bound


@dataclass(frozen=True, slots=True)
class BM25Match:
    """A single BM25 search match."""

    chunk_id: str
    score: float


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer for BM25."""
    assert isinstance(text, str), f"text must be a string, got {type(text).__name__}"
    # Lowercase, split on non-alphanumeric, filter empty
    tokens: list[str] = []
    current: list[str] = []
    max_chars = 1_000_000

    text_lower = text.lower()
    char_count = min(len(text_lower), max_chars)

    for i in range(char_count):
        ch = text_lower[i]
        if ch.isalnum() or ch == "_":
            current.append(ch)
        else:
            if current:
                tokens.append("".join(current))
                current = []

    if current:
        tokens.append("".join(current))

    return tokens


def build_bm25_index(chunks: list[Chunk]) -> dict[str, Any]:
    """Build a BM25 index from chunks. Returns serializable dict."""
    assert len(chunks) <= _MAX_CORPUS_SIZE, (
        f"Corpus size ({len(chunks)}) exceeds maximum ({_MAX_CORPUS_SIZE})"
    )

    corpus: list[list[str]] = []
    chunk_ids: list[str] = []

    for chunk in chunks:
        tokens = _tokenize(chunk.content)
        # Also tokenize metadata text for richer matching
        meta_text = chunk.metadata.to_text()
        meta_tokens = _tokenize(meta_text)
        corpus.append(tokens + meta_tokens)
        chunk_ids.append(chunk.id)

    return {
        "corpus": corpus,
        "chunk_ids": chunk_ids,
    }


def search_bm25(
    query: str,
    index_data: dict[str, Any],
    top_k: int,
) -> list[BM25Match]:
    """Search a BM25 index.

    Args:
        query: Raw query string.
        index_data: BM25 index as returned by build_bm25_index.
        top_k: Number of results to return.

    Returns:
        Top-k matches sorted by descending score.
    """
    assert query, "query must not be empty"
    assert top_k > 0, f"top_k must be > 0, got {top_k}"
    assert "corpus" in index_data, "index_data must contain 'corpus'"
    assert "chunk_ids" in index_data, "index_data must contain 'chunk_ids'"

    corpus = index_data["corpus"]
    chunk_ids = index_data["chunk_ids"]

    assert len(corpus) == len(chunk_ids), (
        f"corpus ({len(corpus)}) and chunk_ids ({len(chunk_ids)}) must have same length"
    )

    if not corpus:
        return []

    bm25 = BM25Okapi(corpus)
    query_tokens = _tokenize(query)

    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)
    assert len(scores) == len(chunk_ids), "Scores length mismatch"

    # Get top-k indices
    n_results = min(top_k, len(scores))
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n_results]

    results: list[BM25Match] = []
    for idx in top_indices:
        score = float(scores[idx])
        if score > 0:
            results.append(BM25Match(chunk_id=chunk_ids[idx], score=score))

    return results


def search_bm25_across_partitions(
    query: str,
    partitions: list[PartitionStore],
    top_k: int,
) -> list[BM25Match]:
    """Search BM25 across multiple partitions and merge results."""
    assert top_k > 0, f"top_k must be > 0, got {top_k}"

    all_matches: list[BM25Match] = []
    for partition in partitions:
        index_data = partition.read_bm25()
        if index_data is None:
            continue
        matches = search_bm25(query, index_data, top_k)
        all_matches.extend(matches)

    all_matches.sort(key=lambda m: m.score, reverse=True)
    return all_matches[:top_k]
