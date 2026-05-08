"""Fallback parser — paragraph-based parsing for unrecognized languages."""

from __future__ import annotations

from dorje.types import ASTContext, Chunk, ChunkMetadata, GraphNode, SemanticUnit, Triple

_MIN_PARAGRAPH_LINES = 3
_MAX_LINES_PER_CHUNK = 100


class FallbackParser:
    """Line-based parsing. Used when no language-specific parser is available."""

    name = "fallback"
    extensions: list[str] = []  # Registered as default, not by extension

    def parse(self, source: str, path: str) -> list[SemanticUnit]:
        """Emit a single module-level semantic unit containing the full file."""
        assert source, "source must not be empty"
        assert path, "path must not be empty"

        lines = source.splitlines(keepends=True)
        total_lines = len(lines)

        if total_lines == 0:
            return []

        module_name = path.replace("/", ".")
        # Strip common extensions
        for ext in (".py", ".js", ".ts", ".java", ".go", ".c", ".h", ".cpp"):
            if module_name.endswith(ext):
                module_name = module_name.removesuffix(ext)
                break

        metadata = _text_metadata(path, 0, total_lines - 1)

        module_unit = SemanticUnit(
            kind="module",
            name=module_name,
            qualified_name=module_name,
            path=path,
            start_line=0,
            end_line=total_lines - 1,
            content=source,
            language=None,
            metadata=metadata,
            parent_unit_id=None,
            pass_name="semantic_unit",
        )

        return [module_unit]

    def extract_ast_context(self, source: str, path: str) -> list[ASTContext]:
        """Fallback has no AST context."""
        return []

    def build_graph(self, source: str, path: str) -> tuple[list[GraphNode], list[Triple]]:
        """Fallback produces no graph data."""
        return [], []


def _split_paragraphs(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Split lines into paragraphs separated by blank lines.

    Returns list of (start_line_index, paragraph_lines).
    """
    paragraphs: list[tuple[int, list[str]]] = []
    current: list[str] = []
    current_start = 0
    total = len(lines)

    for i in range(total):
        line = lines[i]
        if line.strip() == "":
            if current:
                paragraphs.append((current_start, current))
                current = []
        else:
            if not current:
                current_start = i
            current.append(line)

    if current:
        paragraphs.append((current_start, current))

    return paragraphs


def _text_metadata(path: str, start: int, end: int) -> ChunkMetadata:
    """Build minimal metadata for a text chunk."""
    return ChunkMetadata(
        name=None,
        qualified_name=None,
        kind="paragraph",
        parent_name=None,
        parent_kind=None,
        parameters=None,
        return_type=None,
        decorators=None,
        docstring=None,
        visibility=None,
        cyclomatic_branch_count=None,
        imports_used=None,
        calls_made=None,
    )
