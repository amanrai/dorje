"""Mermaid diagram generation from knowledge graph."""

from __future__ import annotations

import re

from dorje.storage import IndexStore
from dorje.types import GraphNode, Triple

_MAX_NODES = 500  # Safety bound
_MAX_TRIPLES = 2000  # Safety bound


def graph_to_mermaid(
    store: IndexStore,
    path_filter: str | None = None,
) -> str:
    """Generate a Mermaid flowchart from the knowledge graph.

    Args:
        store: Loaded IndexStore.
        path_filter: Optional path prefix to filter nodes.

    Returns:
        Mermaid diagram string.
    """
    partitions = store.all_partitions()
    assert partitions, "No partitions found in index"

    # Collect all nodes and triples
    all_nodes: list[GraphNode] = []
    all_triples: list[Triple] = []

    for partition in partitions:
        all_nodes.extend(partition.read_graph_nodes())
        all_triples.extend(partition.read_graph_triples())

    # Apply path filter
    if path_filter and path_filter != ".":
        filtered_ids: set[str] = set()
        filtered_nodes: list[GraphNode] = []
        for node in all_nodes:
            if node.path is not None and node.path.startswith(path_filter):
                filtered_ids.add(node.id)
                filtered_nodes.append(node)
        all_nodes = filtered_nodes

        filtered_triples: list[Triple] = []
        for triple in all_triples:
            if triple.subject in filtered_ids or triple.object in filtered_ids:
                filtered_triples.append(triple)
        all_triples = filtered_triples

    if not all_nodes:
        return "graph LR\n    empty[No graph data]"

    # Truncate for sanity
    all_nodes = all_nodes[:_MAX_NODES]
    all_triples = all_triples[:_MAX_TRIPLES]

    # Build node id set for filtering dangling triples
    node_ids = {n.id for n in all_nodes}

    # Build Mermaid output
    lines: list[str] = ["graph LR"]

    # Node definitions
    for node in all_nodes:
        safe_id = _sanitize_id(node.id)
        safe_label = _escape_label(node.label)
        shape = _shape_for_kind(node.kind)
        lines.append(f"    {safe_id}{shape[0]}{safe_label}{shape[1]}")

    # Edges
    for triple in all_triples:
        if triple.subject not in node_ids or triple.object not in node_ids:
            continue
        subj = _sanitize_id(triple.subject)
        obj = _sanitize_id(triple.object)
        verb = _escape_label(triple.verb)

        if triple.bidirectional:
            lines.append(f"    {subj} <-->|{verb}| {obj}")
        else:
            lines.append(f"    {subj} -->|{verb}| {obj}")

    return "\n".join(lines)


def _sanitize_id(node_id: str) -> str:
    """Make a node ID safe for Mermaid."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", node_id)


def _escape_label(label: str) -> str:
    """Escape a label for Mermaid — replace quotes and brackets."""
    label = label.replace('"', "'")
    label = label.replace("[", "(")
    label = label.replace("]", ")")
    label = label.replace("{", "(")
    label = label.replace("}", ")")
    # Truncate long labels
    max_label = 60
    if len(label) > max_label:
        label = label[:max_label - 3] + "..."
    return f'"{label}"'


def _shape_for_kind(kind: str) -> tuple[str, str]:
    """Return Mermaid shape delimiters based on node kind."""
    shapes: dict[str, tuple[str, str]] = {
        "class": ("[", "]"),        # rectangle
        "module": ("[[", "]]"),     # subroutine
        "function": ("(", ")"),     # rounded
        "method": ("(", ")"),       # rounded
        "import": ("{{", "}}"),     # hexagon
    }
    return shapes.get(kind, ("(", ")"))
