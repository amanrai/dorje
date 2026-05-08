"""Chunking orchestrator — runs extraction passes, collects graph data."""

from __future__ import annotations

from dorje.config import ChunkingConfig
from dorje.discovery import DiscoveredFile
from dorje.passes import count_tokens, flatten_chunks, run_passes
from dorje.types import Chunk, GraphNode, SemanticUnit, Triple


def chunk_file(
    file: DiscoveredFile,
    config: ChunkingConfig,
) -> tuple[list[Chunk], list[GraphNode], list[Triple]]:
    """Parse and chunk a single file. Returns chunks, graph nodes, and triples.

    This is the main entry point for the indexing pipeline per file.
    Runs all registered extraction passes, then collects graph data.
    """
    assert file.absolute_path.is_file(), f"File does not exist: {file.absolute_path}"
    config.validate()

    source = file.absolute_path.read_text(encoding="utf-8", errors="replace")
    if not source.strip():
        return [], [], []

    # Run extraction passes (parse + chunk each unit)
    units = run_passes(source, file.relative_path, None, config)
    chunks = flatten_chunks(units)

    # Extract graph data from parser
    from dorje.parsers import get_parser

    parser = get_parser(file.extension)
    nodes, triples = parser.build_graph(source, file.relative_path)

    assert all(isinstance(c, Chunk) for c in chunks)
    assert all(isinstance(n, GraphNode) for n in nodes)
    assert all(isinstance(t, Triple) for t in triples)

    return chunks, nodes, triples
