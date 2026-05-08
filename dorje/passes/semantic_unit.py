"""Semantic unit extraction pass — modules, functions, classes, methods."""

from __future__ import annotations

from pathlib import Path

from dorje.config import ChunkingConfig
from dorje.passes import default_chunk, register_pass
from dorje.types import CallRef, Chunk, ChunkMetadata, SemanticUnit

_PASS_NAME = "semantic_unit"
_MAX_UNITS = 5000


def _module_name(path: str) -> str:
    """Convert file path to module-style qualified name."""
    return path.replace("/", ".").removesuffix(".py")


def _module_metadata(
    path: str,
    imports: tuple[str, ...],
) -> ChunkMetadata:
    """Build metadata for the module-level semantic unit."""
    name = _module_name(path)
    return ChunkMetadata(
        name=name,
        qualified_name=name,
        kind="module",
        parent_name=None,
        parent_kind=None,
        parameters=None,
        return_type=None,
        decorators=None,
        docstring=None,
        visibility="public",
        cyclomatic_branch_count=None,
        imports_used=imports,
        calls_made=None,
    )


@register_pass
class SemanticUnitPass:
    """Extract module, function, class, and method units from source.

    Order 100 — runs first. Delegates to language-specific parsers for
    AST extraction, then wraps results as SemanticUnits.
    """

    name = _PASS_NAME
    order = 100

    def parse(
        self,
        source: str,
        path: str,
        language: str | None,
        prior_units: list[SemanticUnit],
    ) -> list[SemanticUnit]:
        """Find + read: extract semantic units from source.

        Always emits a module unit (full file) first, then child units.
        """
        assert source, "source must not be empty"
        assert path, "path must not be empty"

        from dorje.parsers import get_parser

        extension = Path(path).suffix.lower()
        parser = get_parser(extension)

        # Get AST contexts from parser
        contexts = parser.extract_ast_context(source, path)
        source_bytes = source.encode("utf-8")
        lines = source.splitlines(keepends=True)
        total_lines = len(lines)

        module_qname = _module_name(path)

        # Collect module-level imports for metadata
        imports: tuple[str, ...] = ()
        if contexts:
            # All contexts share the same imports_used from the module
            first_ctx = contexts[0]
            if hasattr(first_ctx, "imports_used") and first_ctx.imports_used:
                imports = first_ctx.imports_used

        # Module unit — always first, always the full file
        module_unit = SemanticUnit(
            kind="module",
            name=module_qname,
            qualified_name=module_qname,
            path=path,
            start_line=0,
            end_line=max(total_lines - 1, 0),
            content=source,
            language=language or _guess_language(extension),
            metadata=_module_metadata(path, imports),
            parent_unit_id=None,
            pass_name=_PASS_NAME,
        )

        units: list[SemanticUnit] = [module_unit]

        # Child units from AST contexts
        from dorje.parsers.python import (
            _create_parser,
            _find_inner_def,
            _get_name,
        )

        # Re-parse to get node source ranges
        ts_parser = _create_parser()
        tree = ts_parser.parse(source_bytes)

        for ctx in contexts:
            assert len(units) <= _MAX_UNITS, f"Too many units (>{_MAX_UNITS})"

            node = _find_node_in_tree(
                tree.root_node, ctx.name, ctx.kind, extension
            )
            if node is None:
                continue

            start_line = node.start_point[0]
            end_line = node.end_point[0]
            text = "".join(lines[start_line:end_line + 1])

            if not text.strip():
                continue

            # Determine parent
            parent_id = module_qname
            if ctx.parent_name and ctx.parent_kind == "class":
                parent_id = f"{module_qname}.{ctx.parent_name}"

            units.append(SemanticUnit(
                kind=ctx.kind,
                name=ctx.name,
                qualified_name=ctx.qualified_name,
                path=path,
                start_line=start_line,
                end_line=end_line,
                content=text,
                language=language or _guess_language(extension),
                metadata=ctx.to_chunk_metadata(),
                parent_unit_id=parent_id,
                pass_name=_PASS_NAME,
            ))

        return units

    def chunk(
        self,
        unit: SemanticUnit,
        config: ChunkingConfig,
    ) -> list[Chunk]:
        """Split a semantic unit into token-limited chunks using default strategy."""
        return default_chunk(unit, config)


def _guess_language(extension: str) -> str | None:
    """Guess language from file extension."""
    lang_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".rs": "rust",
    }
    return lang_map.get(extension)


def _find_node_in_tree(
    root_node: object,
    name: str,
    kind: str,
    extension: str,
) -> object | None:
    """Find a structural node by name and kind in the AST."""
    if extension != ".py":
        return None

    from dorje.parsers.python import _find_node_by_name

    return _find_node_by_name(root_node, name, kind, depth=0)
