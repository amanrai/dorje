"""File discovery — walks directory trees respecting .gitignore and .dorjeignore."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

# Text file extensions we index in phase 1
_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    # Code
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".h", ".cpp", ".hpp",
    ".cc", ".cxx", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".kts",
    ".scala", ".cs", ".m", ".mm", ".lua", ".pl", ".pm", ".r", ".R",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    # Markup / prose
    ".md", ".markdown", ".rst", ".txt", ".adoc", ".org", ".tex",
    # Config
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".xml", ".html", ".htm", ".css", ".scss", ".sass", ".less",
    # Data
    ".csv", ".tsv", ".sql",
    # Build / CI
    ".dockerfile", ".containerfile", ".makefile",
    ".gradle", ".cmake", ".tf", ".hcl",
})

# Files with no extension that are text
_TEXT_FILENAMES: frozenset[str] = frozenset({
    "Makefile", "Dockerfile", "Containerfile", "Rakefile", "Gemfile",
    "Procfile", "Vagrantfile", "Justfile", ".gitignore", ".dorjeignore",
    ".dockerignore", ".editorconfig", ".env.example",
})

_MAX_FILE_SIZE_BYTES = 1_000_000  # 1MB — skip files larger than this
_MAX_TREE_DEPTH = 100


@dataclass(frozen=True, slots=True)
class DiscoveredFile:
    """A file discovered for indexing."""

    absolute_path: Path
    relative_path: str  # Relative to index root
    extension: str
    size_bytes: int


class IgnoreRules:
    """Parses and applies .gitignore / .dorjeignore rules."""

    def __init__(self) -> None:
        self._patterns: list[tuple[str, bool]] = []  # (pattern, is_negation)

    def load_file(self, path: Path) -> None:
        """Load ignore patterns from a file."""
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("!"):
                self._patterns.append((stripped[1:], True))
            else:
                self._patterns.append((stripped, False))

    def is_ignored(self, relative_path: str, is_dir: bool) -> bool:
        """Check if a path matches any ignore pattern."""
        assert relative_path, "relative_path must not be empty"

        result = False
        name = os.path.basename(relative_path)

        max_patterns = 10_000  # Safety bound
        assert len(self._patterns) <= max_patterns, (
            f"Too many ignore patterns: {len(self._patterns)}"
        )

        for pattern, is_negation in self._patterns:
            matched = False

            # Directory-only pattern
            if pattern.endswith("/"):
                if is_dir:
                    matched = (
                        fnmatch.fnmatch(name, pattern.rstrip("/"))
                        or fnmatch.fnmatch(relative_path, pattern.rstrip("/"))
                    )
            elif "/" in pattern:
                matched = fnmatch.fnmatch(relative_path, pattern)
            else:
                matched = fnmatch.fnmatch(name, pattern)

            if matched:
                result = not is_negation

        return result


def _is_text_file(path: Path) -> bool:
    """Check if a file is a text file we should index."""
    if path.name in _TEXT_FILENAMES:
        return True
    return path.suffix.lower() in _TEXT_EXTENSIONS


def _build_ignore_rules(directory: Path) -> IgnoreRules:
    """Build ignore rules from .gitignore and .dorjeignore in a directory."""
    rules = IgnoreRules()
    rules.load_file(directory / ".gitignore")
    rules.load_file(directory / ".dorjeignore")
    return rules


def discover_files(
    root: Path,
    delegates: list[str] | None = None,
) -> list[DiscoveredFile]:
    """Walk directory tree and discover indexable text files.

    Args:
        root: Absolute path to the directory to scan.
        delegates: Relative paths of subtrees that have their own .dorje index.
                   These are skipped entirely.

    Returns:
        List of discovered files, sorted by relative path.
    """
    assert root.is_absolute(), f"root must be an absolute path, got {root}"
    assert root.is_dir(), f"root must be a directory, got {root}"

    delegates_set = frozenset(delegates or [])
    results: list[DiscoveredFile] = []

    _walk_directory(root, root, delegates_set, results, depth=0)

    results.sort(key=lambda f: f.relative_path)
    return results


def _walk_directory(
    current: Path,
    root: Path,
    delegates: frozenset[str],
    results: list[DiscoveredFile],
    depth: int,
) -> None:
    """Recursive directory walker with ignore rules."""
    assert depth < _MAX_TREE_DEPTH, f"Directory tree exceeds max depth of {_MAX_TREE_DEPTH}"

    rules = _build_ignore_rules(current)

    try:
        entries = sorted(current.iterdir(), key=lambda e: e.name)
    except PermissionError:
        return

    max_entries = 100_000  # Safety bound per directory
    entry_count = 0

    for entry in entries:
        entry_count += 1
        assert entry_count <= max_entries, (
            f"Directory {current} has too many entries (>{max_entries})"
        )

        relative = str(entry.relative_to(root))

        # Skip .dorje directories
        if entry.name == ".dorje":
            continue

        # Skip hidden directories (except those with ignore files)
        if entry.name.startswith(".") and entry.is_dir():
            continue

        # Skip delegated subtrees
        if relative in delegates:
            continue

        is_dir = entry.is_dir()

        # Apply ignore rules
        if rules.is_ignored(relative, is_dir):
            continue

        if is_dir:
            _walk_directory(entry, root, delegates, results, depth + 1)
        elif entry.is_file():
            if not _is_text_file(entry):
                continue

            try:
                size = entry.stat().st_size
            except OSError:
                continue

            if size == 0 or size > _MAX_FILE_SIZE_BYTES:
                continue

            results.append(DiscoveredFile(
                absolute_path=entry,
                relative_path=relative,
                extension=entry.suffix.lower(),
                size_bytes=size,
            ))
