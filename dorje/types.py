"""Core data types for Dorje. All immutable, all slotted (except SemanticUnit)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CallRef:
    """A reference to a called function/method."""

    raw: str  # as written in source, e.g. "close_messaging"
    resolved_unit_id: str | None  # qualified_name of target SemanticUnit, or None


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    """Structured metadata extracted from AST context. Itself embedded as a vector."""

    name: str | None
    qualified_name: str | None
    kind: str  # "function", "method", "class", "module", "paragraph", "commit"
    parent_name: str | None
    parent_kind: str | None
    parameters: tuple[str, ...] | None
    return_type: str | None
    decorators: tuple[str, ...] | None
    docstring: str | None
    visibility: str | None  # "public", "private", "protected"
    cyclomatic_branch_count: int | None
    imports_used: tuple[str, ...] | None
    calls_made: tuple[CallRef, ...] | None

    def to_text(self) -> str:
        """Render as searchable text for metadata embedding."""
        assert self.kind, "ChunkMetadata.kind must not be empty"

        parts: list[str] = []

        # Signature line
        sig = self.kind
        if self.name:
            sig = f"{sig} {self.name}"
        if self.parameters is not None:
            sig = f"{sig}({', '.join(self.parameters)})"
        if self.return_type:
            sig = f"{sig} -> {self.return_type}"
        parts.append(sig)

        # Parent context
        if self.parent_name and self.parent_kind:
            parts.append(f"  in {self.parent_kind} {self.parent_name}")

        # Qualified location
        if self.qualified_name:
            parts.append(f"  qualified: {self.qualified_name}")

        # Visibility
        if self.visibility:
            parts.append(f"  visibility: {self.visibility}")

        # Decorators
        if self.decorators:
            parts.append(f"  decorators: {', '.join(self.decorators)}")

        # Calls
        if self.calls_made:
            call_strs = [
                c.resolved_unit_id if c.resolved_unit_id else c.raw
                for c in self.calls_made
            ]
            parts.append(f"  calls: {', '.join(call_strs)}")

        # Imports
        if self.imports_used:
            parts.append(f"  imports used: {', '.join(self.imports_used)}")

        # Complexity
        if self.cyclomatic_branch_count is not None:
            parts.append(f"  cyclomatic_branch_count: {self.cyclomatic_branch_count}")

        # Docstring
        if self.docstring:
            parts.append(f"  docstring: {self.docstring}")

        assert len(parts) >= 1, "to_text must produce at least a signature line"
        return "\n".join(parts)


def _make_chunk_id(path: str, start_line: int, end_line: int, content: str) -> str:
    """Deterministic chunk ID from path, line range, and content hash."""
    assert path, "path must not be empty"
    assert start_line >= 0, f"start_line must be >= 0, got {start_line}"
    assert end_line >= start_line, f"end_line ({end_line}) must be >= start_line ({start_line})"

    h = hashlib.sha256()
    h.update(path.encode("utf-8"))
    h.update(f":{start_line}:{end_line}:".encode("utf-8"))
    h.update(content.encode("utf-8"))
    return h.hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Chunk:
    """A single indexable unit — code, text, or git history."""

    id: str
    path: str
    start_line: int
    end_line: int
    content: str
    chunk_type: str  # "function", "class", "module", "paragraph", "commit", etc.
    language: str | None
    metadata: ChunkMetadata
    unit_id: str  # qualified_name of owning SemanticUnit
    pass_name: str  # extraction pass that produced the parent unit

    @staticmethod
    def create(
        path: str,
        start_line: int,
        end_line: int,
        content: str,
        chunk_type: str,
        language: str | None,
        metadata: ChunkMetadata,
        unit_id: str = "",
        pass_name: str = "",
    ) -> Chunk:
        """Factory with deterministic ID generation."""
        assert path, "path must not be empty"
        assert content, "content must not be empty"
        assert chunk_type, "chunk_type must not be empty"

        chunk_id = _make_chunk_id(path, start_line, end_line, content)
        return Chunk(
            id=chunk_id,
            path=path,
            start_line=start_line,
            end_line=end_line,
            content=content,
            chunk_type=chunk_type,
            language=language,
            metadata=metadata,
            unit_id=unit_id,
            pass_name=pass_name,
        )


@dataclass(slots=True)
class SemanticUnit:
    """A logical code entity — module, function, class, method.

    Produced by an extraction pass. Each unit owns 1+ physical Chunks
    after token limiting. The qualified_name serves as graph identity.
    """

    kind: str  # "module", "function", "class", "method", "paragraph"
    name: str
    qualified_name: str  # graph identity, e.g. "dorje.cli.main"
    path: str  # relative file path
    start_line: int
    end_line: int
    content: str  # raw source text (before token limiting)
    language: str | None
    metadata: ChunkMetadata
    parent_unit_id: str | None  # qualified_name of parent (None for module)
    pass_name: str  # extraction pass that produced this unit
    chunks: list[Chunk] = field(default_factory=list)  # populated by chunker


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single result from the search pipeline."""

    chunk: Chunk
    score: float
    source: str  # "vector", "bm25", "graph"
    highlights: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphNode:
    """A node in the knowledge graph — code symbol or abstract concept."""

    id: str
    kind: str  # "function", "class", "module", "import", "concept", "feature"
    label: str
    path: str | None  # None for abstract concepts
    line: int | None  # None for abstract concepts
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class Triple:
    """A (subject, verb, object) relationship in the knowledge graph."""

    subject: str  # Node id
    verb: str  # Freeform: "calls", "depends on", "implements", etc.
    object: str  # Node id
    source: str  # "ast" or "llm"
    bidirectional: bool
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class ASTContext:
    """Raw AST extraction before it becomes ChunkMetadata."""

    name: str
    qualified_name: str
    kind: str
    parent_name: str | None
    parent_kind: str | None
    module_path: str
    parameters: tuple[str, ...]
    return_type: str | None
    decorators: tuple[str, ...]
    docstring: str | None
    visibility: str
    cyclomatic_branch_count: int
    imports_used: tuple[str, ...]
    calls_made: tuple[str, ...]

    def to_chunk_metadata(self) -> ChunkMetadata:
        """Convert AST context to chunk metadata.

        Calls are wrapped as unresolved CallRefs — resolution happens in pass 2.
        """
        call_refs = tuple(
            CallRef(raw=c, resolved_unit_id=None) for c in self.calls_made
        )
        return ChunkMetadata(
            name=self.name,
            qualified_name=self.qualified_name,
            kind=self.kind,
            parent_name=self.parent_name,
            parent_kind=self.parent_kind,
            parameters=self.parameters,
            return_type=self.return_type,
            decorators=self.decorators,
            docstring=self.docstring,
            visibility=self.visibility,
            cyclomatic_branch_count=self.cyclomatic_branch_count,
            imports_used=self.imports_used,
            calls_made=call_refs,
        )
