"""Extraction pass pipeline — registry, orchestration, and default chunking."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import tiktoken

from dorje.config import ChunkingConfig
from dorje.types import Chunk, ChunkMetadata, SemanticUnit

_PASS_REGISTRY: list[type[ExtractionPass]] = []
_MAX_PASSES = 50
_MAX_UNITS_PER_PASS = 10_000

_ENCODING_NAME = "cl100k_base"
_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    """Lazy-load the tiktoken encoding."""
    global _encoding  # noqa: PLW0603
    if _encoding is None:
        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoding


def count_tokens(text: str) -> int:
    """Count tokens in a text string."""
    assert isinstance(text, str), f"text must be a string, got {type(text).__name__}"
    enc = _get_encoding()
    return len(enc.encode(text))


@runtime_checkable
class ExtractionPass(Protocol):
    """Protocol for extraction passes.

    Each pass has two phases:
      parse()  — find units in source, read their content → list[SemanticUnit]
      chunk()  — split a single unit into token-limited physical chunks → list[Chunk]
    """

    name: str
    order: int  # execution order (lower = earlier)

    def parse(
        self,
        source: str,
        path: str,
        language: str | None,
        prior_units: list[SemanticUnit],
    ) -> list[SemanticUnit]:
        """Find + read: locate semantic units in source, extract their content."""
        ...

    def chunk(
        self,
        unit: SemanticUnit,
        config: ChunkingConfig,
    ) -> list[Chunk]:
        """Split a single semantic unit into token-limited physical chunks."""
        ...


def register_pass(cls: type[ExtractionPass]) -> type[ExtractionPass]:
    """Decorator to register an extraction pass."""
    assert hasattr(cls, "name"), f"Pass {cls.__name__} must have 'name' attribute"
    assert hasattr(cls, "order"), f"Pass {cls.__name__} must have 'order' attribute"
    assert len(_PASS_REGISTRY) < _MAX_PASSES, f"Too many passes (>{_MAX_PASSES})"

    _PASS_REGISTRY.append(cls)
    return cls


def registered_passes() -> list[ExtractionPass]:
    """Return all registered passes, sorted by order."""
    instances = [cls() for cls in _PASS_REGISTRY]
    instances.sort(key=lambda p: p.order)
    return instances


def run_passes(
    source: str,
    path: str,
    language: str | None,
    config: ChunkingConfig,
) -> list[SemanticUnit]:
    """Run all registered extraction passes in order.

    Each pass:
      1. parse() — produces semantic units from source
      2. chunk() — splits each unit into physical chunks

    Later passes receive all units from earlier passes as context.
    """
    assert source, "source must not be empty"
    assert path, "path must not be empty"

    passes = registered_passes()
    all_units: list[SemanticUnit] = []

    for pass_ in passes:
        new_units = pass_.parse(source, path, language, all_units)
        assert len(new_units) <= _MAX_UNITS_PER_PASS, (
            f"Pass '{pass_.name}' produced too many units ({len(new_units)})"
        )

        for unit in new_units:
            chunks = pass_.chunk(unit, config)
            unit.chunks = chunks

        all_units.extend(new_units)

    return all_units


def flatten_chunks(units: list[SemanticUnit]) -> list[Chunk]:
    """Extract all physical chunks from a list of semantic units."""
    result: list[Chunk] = []
    for unit in units:
        result.extend(unit.chunks)
    return result


# --- Default chunking (token-limit + stride) ---


def default_chunk(unit: SemanticUnit, config: ChunkingConfig) -> list[Chunk]:
    """Default chunking strategy: token-limit splitting with stride overlap.

    Passes can call this or implement their own chunk() method.
    """
    assert unit.content, "unit content must not be empty"

    token_count = count_tokens(unit.content)

    if token_count <= config.max_tokens:
        return [Chunk.create(
            path=unit.path,
            start_line=unit.start_line,
            end_line=unit.end_line,
            content=unit.content,
            chunk_type=unit.kind,
            language=unit.language,
            metadata=unit.metadata,
            unit_id=unit.qualified_name,
            pass_name=unit.pass_name,
        )]

    return _stride_unit(unit, config)


def _stride_unit(unit: SemanticUnit, config: ChunkingConfig) -> list[Chunk]:
    """Split an oversized unit using striding with context retention."""
    lines = unit.content.splitlines(keepends=True)
    total_lines = len(lines)

    if total_lines == 0:
        return []

    # Build a header from signature lines (function/class)
    header_lines: list[str] = []
    if unit.kind in ("function", "method", "class"):
        max_header = 5
        for i in range(min(max_header, total_lines)):
            header_lines.append(lines[i])
            if ":" in lines[i] or "{" in lines[i]:
                break

    header = "".join(header_lines)
    header_tokens = count_tokens(header) if header else 0
    available_tokens = config.max_tokens - header_tokens

    assert available_tokens > 0, (
        f"Header alone ({header_tokens} tokens) exceeds max_tokens ({config.max_tokens})"
    )

    result: list[Chunk] = []
    body_start = len(header_lines)
    offset = body_start
    stride_lines = _tokens_to_approx_lines(config.stride_tokens)
    max_splits = 100  # Safety bound

    for split_idx in range(max_splits):
        if offset >= total_lines:
            break

        chunk_lines = list(header_lines) if split_idx > 0 else []
        end = offset

        max_line_scan = total_lines - offset + 1
        for _ in range(max_line_scan):
            if end >= total_lines:
                break
            test_content = "".join(chunk_lines) + lines[end]
            if count_tokens(test_content) > config.max_tokens and chunk_lines:
                break
            chunk_lines.append(lines[end])
            end += 1

        content = "".join(chunk_lines)
        if content.strip():
            start_line = unit.start_line + (0 if split_idx == 0 else offset)
            end_line = unit.start_line + end - 1

            result.append(Chunk.create(
                path=unit.path,
                start_line=start_line,
                end_line=end_line,
                content=content,
                chunk_type=unit.kind,
                language=unit.language,
                metadata=unit.metadata,
                unit_id=unit.qualified_name,
                pass_name=unit.pass_name,
            ))

        offset = max(end - stride_lines, offset + 1)

    return result


def _tokens_to_approx_lines(tokens: int) -> int:
    """Approximate token count to line count. ~10 tokens per line."""
    assert tokens > 0, f"tokens must be > 0, got {tokens}"
    return max(tokens // 10, 1)


def _load_all_passes() -> None:
    """Import all pass modules to trigger registration."""
    import dorje.passes.semantic_unit  # noqa: F401
    import dorje.passes.call_resolution  # noqa: F401


_load_all_passes()
