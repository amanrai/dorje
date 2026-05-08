"""Call resolution pass — resolves raw call names to semantic unit IDs."""

from __future__ import annotations

from dorje.config import ChunkingConfig
from dorje.passes import default_chunk, register_pass
from dorje.types import CallRef, Chunk, ChunkMetadata, SemanticUnit

_PASS_NAME = "call_resolution"
_MAX_UNITS = 10_000


def _build_resolution_map(units: list[SemanticUnit]) -> dict[str, str]:
    """Build name -> qualified_name map from prior units.

    Indexes by:
      - bare name ("foo")
      - Class.method ("MyClass.foo")
      - full qualified_name ("dorje.cli.MyClass.foo")

    Ambiguous bare names (same name in multiple units) are NOT indexed
    to avoid incorrect resolution.
    """
    assert len(units) <= _MAX_UNITS, f"Too many units (>{_MAX_UNITS})"

    by_bare: dict[str, list[str]] = {}
    by_qualified: dict[str, str] = {}

    for unit in units:
        if unit.kind == "module":
            continue

        qname = unit.qualified_name
        bare = unit.name

        # Always index by full qualified_name
        by_qualified[qname] = qname

        # Index by bare name (detect ambiguity)
        if bare not in by_bare:
            by_bare[bare] = []
        by_bare[bare].append(qname)

        # Index by Parent.name for methods
        if unit.parent_unit_id:
            parts = unit.parent_unit_id.rsplit(".", 1)
            if len(parts) == 2:
                parent_bare = parts[1]
                dotted = f"{parent_bare}.{bare}"
                by_qualified[dotted] = qname

    # Only include unambiguous bare names
    result: dict[str, str] = dict(by_qualified)
    for bare, qnames in by_bare.items():
        if len(qnames) == 1:
            result[bare] = qnames[0]

    return result


def _resolve_one(raw: str, resolution_map: dict[str, str]) -> str | None:
    """Try to resolve a single raw call name.

    Attempts in order:
      1. Exact match: "close_messaging" -> map["close_messaging"]
      2. Dotted call: "asyncio.create_task" -> map["asyncio"] + ".create_task"
         (first component matched against imports, rest appended)
      3. Method call: "self.foo" or "obj.bar" -> map["bar"] (try tail as bare name)
    """
    # 1. Exact match
    exact = resolution_map.get(raw)
    if exact is not None:
        return exact

    if "." not in raw:
        return None

    parts = raw.split(".")

    # 2. Dotted call — resolve first component via imports
    head = parts[0]
    tail = ".".join(parts[1:])
    head_resolved = resolution_map.get(head)
    if head_resolved is not None:
        return f"{head_resolved}.{tail}"

    # 3. Method call — try the last component as a bare name
    #    e.g. "self.close_messaging" -> resolve "close_messaging"
    last = parts[-1]
    last_resolved = resolution_map.get(last)
    if last_resolved is not None:
        return last_resolved

    return None


def _resolve_calls(
    metadata: ChunkMetadata,
    resolution_map: dict[str, str],
) -> ChunkMetadata | None:
    """Resolve CallRefs in metadata. Returns new metadata if any changed, else None."""
    if not metadata.calls_made:
        return None

    changed = False
    resolved_calls: list[CallRef] = []
    max_calls = 500

    for i, call in enumerate(metadata.calls_made):
        assert i < max_calls, f"Too many calls (>{max_calls})"

        if call.resolved_unit_id is not None:
            resolved_calls.append(call)
            continue

        target = _resolve_one(call.raw, resolution_map)
        if target is not None:
            resolved_calls.append(CallRef(raw=call.raw, resolved_unit_id=target))
            changed = True
        else:
            resolved_calls.append(call)

    if not changed:
        return None

    return ChunkMetadata(
        name=metadata.name,
        qualified_name=metadata.qualified_name,
        kind=metadata.kind,
        parent_name=metadata.parent_name,
        parent_kind=metadata.parent_kind,
        parameters=metadata.parameters,
        return_type=metadata.return_type,
        decorators=metadata.decorators,
        docstring=metadata.docstring,
        visibility=metadata.visibility,
        cyclomatic_branch_count=metadata.cyclomatic_branch_count,
        imports_used=metadata.imports_used,
        calls_made=tuple(resolved_calls),
    )


@register_pass
class CallResolutionPass:
    """Resolve raw call names to semantic unit qualified_names.

    Order 200 — runs after semantic unit extraction (order 100).
    Does not produce new units. Mutates CallRef.resolved_unit_id
    on existing units from prior passes.
    """

    name = _PASS_NAME
    order = 200

    def parse(
        self,
        source: str,
        path: str,
        language: str | None,
        prior_units: list[SemanticUnit],
    ) -> list[SemanticUnit]:
        """Resolve calls in prior units. Returns empty list (no new units)."""
        if not prior_units:
            return []

        resolution_map = _build_resolution_map(prior_units)

        # Add import-based resolution (language-specific)
        import_map = _extract_import_map(source, path)
        resolution_map.update(import_map)

        for unit in prior_units:
            updated = _resolve_calls(unit.metadata, resolution_map)
            if updated is not None:
                unit.metadata = updated

            # Also resolve calls in chunk metadata
            for chunk in unit.chunks:
                chunk_updated = _resolve_calls(chunk.metadata, resolution_map)
                if chunk_updated is not None:
                    # Chunk is frozen — rebuild it
                    _replace_chunk_metadata(unit, chunk, chunk_updated)

        return []

    def chunk(
        self,
        unit: SemanticUnit,
        config: ChunkingConfig,
    ) -> list[Chunk]:
        """No new units, so no chunking needed."""
        return default_chunk(unit, config)


def _replace_chunk_metadata(
    unit: SemanticUnit,
    old_chunk: Chunk,
    new_metadata: ChunkMetadata,
) -> None:
    """Replace a frozen chunk with updated metadata in the unit's chunk list."""
    new_chunk = Chunk(
        id=old_chunk.id,
        path=old_chunk.path,
        start_line=old_chunk.start_line,
        end_line=old_chunk.end_line,
        content=old_chunk.content,
        chunk_type=old_chunk.chunk_type,
        language=old_chunk.language,
        metadata=new_metadata,
        unit_id=old_chunk.unit_id,
        pass_name=old_chunk.pass_name,
    )
    max_chunks = 10_000
    for i in range(min(len(unit.chunks), max_chunks)):
        if unit.chunks[i] is old_chunk:
            unit.chunks[i] = new_chunk
            return


def _extract_import_map(source: str, path: str) -> dict[str, str]:
    """Extract local_name -> qualified_origin map from source imports.

    Delegates to language-specific parsers. For unsupported languages,
    returns an empty map.
    """
    from pathlib import Path as _Path

    extension = _Path(path).suffix.lower()

    if extension == ".py":
        from dorje.parsers.python import _collect_import_map, _create_parser

        parser = _create_parser()
        tree = parser.parse(source.encode("utf-8"))
        assert tree.root_node is not None, "Failed to parse source"
        return _collect_import_map(tree.root_node, file_path=path)

    return {}
