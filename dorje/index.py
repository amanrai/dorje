"""Indexing pipeline — discovery, chunking, embedding, storage."""

from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from dorje.bm25_search import build_bm25_index
from dorje.chunker import chunk_file
from dorje.config import Config
from dorje.discovery import DiscoveredFile, discover_files
from dorje.embedder import Embedder
from dorje.storage import IndexStore, _partition_key
from dorje.types import Chunk, GraphNode, Triple

_MAX_FILES_PER_INDEX = 500_000  # Safety bound
_BAR_WIDTH = 40


def _progress(label: str, current: int, total: int) -> None:
    """Write a progress bar to stderr."""
    assert total > 0, "total must be > 0"
    frac = min(current / total, 1.0)
    filled = int(_BAR_WIDTH * frac)
    bar = "█" * filled + "░" * (_BAR_WIDTH - filled)
    sys.stderr.write(f"\r{label} [{bar}] {current}/{total}")
    if current >= total:
        sys.stderr.write("\n")
    sys.stderr.flush()


def build_index(
    root: Path,
    config: Config,
    embedder: Embedder,
) -> IndexStore:
    """Build a complete index for a directory.

    Args:
        root: Absolute path to the directory to index.
        config: Dorje configuration.
        embedder: Embedding client.

    Returns:
        The populated IndexStore.
    """
    assert root.is_absolute(), f"root must be absolute, got {root}"
    assert root.is_dir(), f"root must be a directory, got {root}"
    config.validate()

    index_path = root / ".dorje"
    store = IndexStore(index_path)
    store.initialize()

    # Discover files
    sys.stderr.write("Discovering files...\n")
    files = discover_files(root, delegates=store.scope.delegates)
    assert len(files) <= _MAX_FILES_PER_INDEX, (
        f"Too many files ({len(files)} > {_MAX_FILES_PER_INDEX})"
    )
    sys.stderr.write(f"Found {len(files)} files\n")

    if not files:
        return store

    # Chunk files (parallel)
    sys.stderr.write("Chunking...\n")
    workers = config.concurrency.effective_workers()
    all_chunks, all_nodes, all_triples = _chunk_all_files(files, config, workers)
    sys.stderr.write(f"{len(all_chunks)} chunks, {len(all_nodes)} nodes, {len(all_triples)} triples\n")

    if not all_chunks:
        return store

    # Group by partition
    partitioned = _group_by_partition(all_chunks, all_nodes, all_triples)
    total_partitions = len(partitioned)

    # Embed and store each partition
    partition_mapping: dict[str, str] = {}

    for i, (partition_key, (chunks, nodes, triples)) in enumerate(partitioned.items()):
        _progress("Embedding", i + 1, total_partitions)

        partition_store = store.partition_for(chunks[0].path)
        partition_mapping[partition_key] = partition_store._path.name

        # Embed content and metadata
        content_texts = [c.content for c in chunks]
        metadata_texts = [c.metadata.to_text() for c in chunks]
        chunk_ids = [c.id for c in chunks]

        content_vectors = embedder.embed(content_texts)
        metadata_vectors = embedder.embed(metadata_texts)

        # Store vectors
        partition_store.write_vectors(chunk_ids, content_vectors, metadata_vectors)

        # Store chunk metadata
        partition_store.write_chunks(chunks)

        # Build and store BM25 index
        bm25_data = build_bm25_index(chunks)
        partition_store.write_bm25(bm25_data)

        # Store graph
        if nodes or triples:
            partition_store.write_graph(nodes, triples)
            _embed_and_store_graph(partition_store, nodes, triples, embedder)

    # Save partition mapping and state
    store.save_partition_mapping(partition_mapping)
    _save_file_hashes(store, files)
    sys.stderr.write("Done.\n")

    return store


def update_index(
    root: Path,
    config: Config,
    embedder: Embedder,
) -> IndexStore:
    """Incrementally update an existing index.

    Only re-indexes files that have changed since the last index.
    """
    assert root.is_absolute(), f"root must be absolute, got {root}"
    assert root.is_dir(), f"root must be a directory, got {root}"

    index_path = root / ".dorje"
    store = IndexStore(index_path)

    if not index_path.exists():
        return build_index(root, config, embedder)

    store.load()

    # Get current file hashes
    files = discover_files(root, delegates=store.scope.delegates)
    current_hashes = _compute_file_hashes(files)

    # Compare with stored hashes
    state = store.read_state()
    stored_hashes: dict[str, str] = state.get("file_hashes", {})

    changed_files: list[DiscoveredFile] = []
    for file in files:
        old_hash = stored_hashes.get(file.relative_path)
        new_hash = current_hashes.get(file.relative_path)
        if old_hash != new_hash:
            changed_files.append(file)

    if not changed_files:
        return store

    # Re-chunk only changed files
    workers = config.concurrency.effective_workers()
    new_chunks, new_nodes, new_triples = _chunk_all_files(changed_files, config, workers)

    if not new_chunks:
        _save_file_hashes(store, files)
        return store

    # Group and re-index affected partitions
    partitioned = _group_by_partition(new_chunks, new_nodes, new_triples)

    for partition_key, (chunks, nodes, triples) in partitioned.items():
        partition_store = store.partition_for(chunks[0].path)

        content_texts = [c.content for c in chunks]
        metadata_texts = [c.metadata.to_text() for c in chunks]
        chunk_ids = [c.id for c in chunks]

        content_vectors = embedder.embed(content_texts)
        metadata_vectors = embedder.embed(metadata_texts)

        partition_store.write_vectors(chunk_ids, content_vectors, metadata_vectors)
        partition_store.write_chunks(chunks)

        bm25_data = build_bm25_index(chunks)
        partition_store.write_bm25(bm25_data)

        if nodes or triples:
            partition_store.write_graph(nodes, triples)
            _embed_and_store_graph(partition_store, nodes, triples, embedder)

    _save_file_hashes(store, files)
    return store


def _chunk_single_file(
    args: tuple[str, str, str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Worker function for parallel chunking.

    Takes serializable args instead of dataclass objects for multiprocessing.
    Returns serializable dicts.
    """
    abs_path_str, rel_path, extension, max_tokens = args

    from dorje.chunker import chunk_file
    from dorje.config import ChunkingConfig
    from dorje.discovery import DiscoveredFile

    abs_path = Path(abs_path_str)
    if not abs_path.is_file():
        return [], [], []

    file = DiscoveredFile(
        absolute_path=abs_path,
        relative_path=rel_path,
        extension=extension,
        size_bytes=abs_path.stat().st_size,
    )

    config = ChunkingConfig(max_tokens=max_tokens)

    try:
        chunks, nodes, triples = chunk_file(file, config)
    except Exception:
        return [], [], []

    from dataclasses import asdict
    chunks_dicts = [asdict(c) for c in chunks]
    nodes_dicts = [asdict(n) for n in nodes]
    triples_dicts = [asdict(t) for t in triples]

    return chunks_dicts, nodes_dicts, triples_dicts


def _chunk_all_files(
    files: list[DiscoveredFile],
    config: Config,
    workers: int,
) -> tuple[list[Chunk], list[GraphNode], list[Triple]]:
    """Chunk all files in parallel."""
    assert workers > 0, f"workers must be > 0, got {workers}"

    args_list = [
        (str(f.absolute_path), f.relative_path, f.extension, config.chunking.max_tokens)
        for f in files
    ]

    all_chunks: list[Chunk] = []
    all_nodes: list[GraphNode] = []
    all_triples: list[Triple] = []

    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_chunk_single_file, args_list, chunksize=10)

        for chunks_dicts, nodes_dicts, triples_dicts in results:
            for cd in chunks_dicts:
                meta = cd.pop("metadata")
                from dorje.types import ChunkMetadata
                chunk_meta = ChunkMetadata(**meta)
                all_chunks.append(Chunk(**{**cd, "metadata": chunk_meta}))

            for nd in nodes_dicts:
                all_nodes.append(GraphNode(**nd))

            for td in triples_dicts:
                all_triples.append(Triple(**td))

    return all_chunks, all_nodes, all_triples


def _group_by_partition(
    chunks: list[Chunk],
    nodes: list[GraphNode],
    triples: list[Triple],
) -> dict[str, tuple[list[Chunk], list[GraphNode], list[Triple]]]:
    """Group chunks, nodes, and triples by partition key."""
    groups: dict[str, tuple[list[Chunk], list[GraphNode], list[Triple]]] = {}

    for chunk in chunks:
        key = _partition_key(chunk.path)
        if key not in groups:
            groups[key] = ([], [], [])
        groups[key][0].append(chunk)

    for node in nodes:
        if node.path is None:
            continue
        key = _partition_key(node.path)
        if key not in groups:
            groups[key] = ([], [], [])
        groups[key][1].append(node)

    for triple in triples:
        # Triples go to the partition of the subject's node
        # For simplicity, use _root if we can't determine
        key = "_root"
        for chunk in chunks:
            if chunk.path and triple.subject.startswith(
                chunk.path.replace("/", ".").removesuffix(".py")
            ):
                key = _partition_key(chunk.path)
                break
        if key not in groups:
            groups[key] = ([], [], [])
        groups[key][2].append(triple)

    return groups


def _embed_and_store_graph(
    partition: Any,
    nodes: list[GraphNode],
    triples: list[Triple],
    embedder: Embedder,
) -> None:
    """Embed graph node labels and verb strings, store vectors."""
    if nodes:
        node_ids = [n.id for n in nodes]
        node_texts = [n.label for n in nodes]
        node_vectors = embedder.embed(node_texts)
        partition.write_graph_vectors("node", node_ids, node_vectors)

    if triples:
        # Deduplicate verbs
        unique_verbs = list(dict.fromkeys(t.verb for t in triples))
        verb_vectors = embedder.embed(unique_verbs)
        partition.write_graph_vectors("verb", unique_verbs, verb_vectors)


def _compute_file_hashes(files: list[DiscoveredFile]) -> dict[str, str]:
    """Compute content hashes for all files."""
    hashes: dict[str, str] = {}
    for file in files:
        try:
            content = file.absolute_path.read_bytes()
            h = hashlib.sha256(content).hexdigest()[:16]
            hashes[file.relative_path] = h
        except OSError:
            continue
    return hashes


def _save_file_hashes(store: IndexStore, files: list[DiscoveredFile]) -> None:
    """Save file hashes to index state."""
    hashes = _compute_file_hashes(files)
    state = store.read_state()
    state["file_hashes"] = hashes
    store.write_state(state)
