"""Standalone parser runner — python -m dorje.parsers <file>

Phase 1: prints all semantic units (module + functions/classes/methods).
Phase 2: steps through each unit one at a time. Press Enter to see its chunks.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dorje.types import Chunk, SemanticUnit

_MAX_UNITS = 5000


def _print_metadata(meta: object, indent: str = "    ") -> None:
    """Print ChunkMetadata fields that have values."""
    from dorje.types import ChunkMetadata

    assert isinstance(meta, ChunkMetadata)

    fields = [
        ("qualified_name", meta.qualified_name),
        ("parent", f"{meta.parent_kind} {meta.parent_name}" if meta.parent_name else None),
        ("visibility", meta.visibility),
        ("parameters", ", ".join(meta.parameters) if meta.parameters else None),
        ("return_type", meta.return_type),
        ("decorators", ", ".join(meta.decorators) if meta.decorators else None),
        ("cyclomatic_branch_count", str(meta.cyclomatic_branch_count) if meta.cyclomatic_branch_count is not None else None),
        ("calls", None),  # handled separately below
        ("imports", ", ".join(meta.imports_used) if meta.imports_used else None),
        ("docstring", meta.docstring[:80] + "..." if meta.docstring and len(meta.docstring) > 80 else meta.docstring),
    ]

    for label, value in fields:
        if value:
            sys.stdout.write(f"{indent}{label}: {value}\n")

    # Calls: one per line, showing resolution status
    if meta.calls_made:
        sys.stdout.write(f"{indent}calls:\n")
        max_calls = 500
        for i, c in enumerate(meta.calls_made):
            assert i < max_calls, f"Too many calls (>{max_calls})"
            if c.resolved_unit_id:
                sys.stdout.write(f"{indent}  {c.raw} -> {c.resolved_unit_id}\n")
            else:
                sys.stdout.write(f"{indent}  {c.raw}\n")


def _print_unit_summary(idx: int, total: int, unit: SemanticUnit) -> None:
    """Print a one-line summary of a semantic unit."""
    sig = f"  [{idx}/{total}] [{unit.kind}] {unit.qualified_name}"
    if unit.metadata.parameters is not None:
        sig += f"({', '.join(unit.metadata.parameters)})"
    if unit.metadata.return_type:
        sig += f" -> {unit.metadata.return_type}"
    if unit.metadata.visibility:
        sig += f"  ({unit.metadata.visibility})"
    sig += f"  <{unit.pass_name}>"

    sys.stdout.write(sig + "\n")


def _print_chunk(idx: int, total: int, chunk: Chunk) -> None:
    """Print a chunk with header and content."""
    header = (
        f"  chunk {idx}/{total}: {chunk.chunk_type} "
        f"[{chunk.path}:{chunk.start_line}-{chunk.end_line}]"
    )
    if chunk.metadata.name:
        header += f" ({chunk.metadata.name})"
    header += f"  unit={chunk.unit_id} pass={chunk.pass_name}"

    sys.stdout.write(header + "\n")
    for line in chunk.content.splitlines():
        sys.stdout.write(f"    {line}\n")
    sys.stdout.write("\n")


def _wait_for_enter() -> bool:
    """Wait for Enter. Returns False if user wants to quit."""
    try:
        sys.stdin.readline()
        return True
    except (EOFError, KeyboardInterrupt):
        sys.stdout.write("\n")
        return False


def main() -> None:
    """Entry point for standalone parser execution."""
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python -m dorje.parsers <file>\n")
        sys.exit(1)

    file_path = Path(sys.argv[1]).resolve()
    assert file_path.is_file(), f"Not a file: {file_path}"

    extension = file_path.suffix.lower()
    source = file_path.read_text(encoding="utf-8", errors="replace")
    assert source.strip(), f"File is empty: {file_path}"

    try:
        relative = str(file_path.relative_to(Path.cwd()))
    except ValueError:
        relative = str(file_path)

    from dorje.config import ChunkingConfig
    from dorje.passes import count_tokens, flatten_chunks, run_passes

    config = ChunkingConfig()

    # Run all extraction passes
    units = run_passes(source, relative, None, config)
    assert len(units) <= _MAX_UNITS, f"Too many units (>{_MAX_UNITS})"

    # Phase 1: show all semantic units
    sys.stdout.write(f"\nFile:   {relative}\n")
    sys.stdout.write(f"Units:  {len(units)}\n\n")

    for i, unit in enumerate(units):
        _print_unit_summary(i + 1, len(units), unit)

    # Phase 2: step through each unit, show chunks on Enter
    all_chunks = flatten_chunks(units)

    sys.stdout.write(
        f"\n{len(all_chunks)} total chunks. "
        f"Press Enter to step through each unit's chunks (Ctrl-C to quit)...\n"
    )

    for i, unit in enumerate(units):
        sys.stdout.write(f"\n{'=' * 60}\n")
        _print_unit_summary(i + 1, len(units), unit)

        tokens = count_tokens(unit.content)
        sys.stdout.write(
            f"  {len(unit.chunks)} chunk(s), ~{tokens} tokens\n"
        )
        sys.stdout.write(f"  file: {unit.path}\n")
        sys.stdout.write(f"  start_line: {unit.start_line}\n")
        sys.stdout.write(f"  end_line: {unit.end_line}\n")
        if unit.parent_unit_id:
            sys.stdout.write(f"  parent: {unit.parent_unit_id}\n")
        sys.stdout.write(f"  metadata:\n")
        _print_metadata(unit.metadata)
        sys.stdout.write(f"  [Enter] show chunks")
        sys.stdout.flush()

        if not _wait_for_enter():
            return

        for j, chunk in enumerate(unit.chunks):
            _print_chunk(j + 1, len(unit.chunks), chunk)

    sys.stdout.write(f"{'=' * 60}\n")
    sys.stdout.write(f"Done. {len(all_chunks)} total chunks across {len(units)} units\n")


if __name__ == "__main__":
    main()
