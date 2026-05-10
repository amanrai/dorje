"""Dorje content/media type detection."""

from __future__ import annotations

import mimetypes
from pathlib import Path

CODE_EXTENSION_MEDIA_TYPES: dict[str, str] = {
    ".py": "text/x-code-python",
    ".pyi": "text/x-code-python",
    ".js": "text/x-code-javascript",
    ".jsx": "text/x-code-jsx",
    ".mjs": "text/x-code-javascript",
    ".cjs": "text/x-code-javascript",
    ".ts": "text/x-code-typescript",
    ".tsx": "text/x-code-tsx",
    ".css": "text/x-code-css",
    ".scss": "text/x-code-scss",
    ".sass": "text/x-code-sass",
    ".less": "text/x-code-less",
    ".vue": "text/x-code-vue",
    ".svelte": "text/x-code-svelte",
    ".astro": "text/x-code-astro",
    ".java": "text/x-code-java",
    ".c": "text/x-code-c",
    ".h": "text/x-code-c",
    ".cpp": "text/x-code-cpp",
    ".cc": "text/x-code-cpp",
    ".cxx": "text/x-code-cpp",
    ".hpp": "text/x-code-cpp",
    ".rs": "text/x-code-rust",
    ".go": "text/x-code-go",
    ".rb": "text/x-code-ruby",
    ".php": "text/x-code-php",
    ".swift": "text/x-code-swift",
    ".kt": "text/x-code-kotlin",
    ".kts": "text/x-code-kotlin",
    ".scala": "text/x-code-scala",
    ".sh": "text/x-code-shell",
    ".bash": "text/x-code-shell",
    ".zsh": "text/x-code-shell",
    ".fish": "text/x-code-shell",
    ".sql": "text/x-code-sql",
    ".r": "text/x-code-r",
    ".R": "text/x-code-r",
    ".jl": "text/x-code-julia",
    ".lua": "text/x-code-lua",
    ".pl": "text/x-code-perl",
    ".ex": "text/x-code-elixir",
    ".exs": "text/x-code-elixir",
    ".erl": "text/x-code-erlang",
    ".hrl": "text/x-code-erlang",
    ".fs": "text/x-code-fsharp",
    ".fsx": "text/x-code-fsharp",
    ".cs": "text/x-code-csharp",
    ".clj": "text/x-code-clojure",
    ".cljs": "text/x-code-clojure",
    ".hs": "text/x-code-haskell",
    ".ml": "text/x-code-ocaml",
    ".mli": "text/x-code-ocaml",
}

TEXT_EXTENSION_MEDIA_TYPES: dict[str, str] = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".mdx": "text/markdown",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
    ".xhtml": "application/xhtml+xml",
    ".xml": "application/xml",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".ndjson": "application/x-ndjson",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".toml": "application/toml",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
}


def guess_content_type(path: str | Path) -> str:
    """Guess a stable Dorje media/content type from a path."""
    suffix = Path(path).suffix
    lower_suffix = suffix.lower()
    if suffix in CODE_EXTENSION_MEDIA_TYPES:
        return CODE_EXTENSION_MEDIA_TYPES[suffix]
    if lower_suffix in CODE_EXTENSION_MEDIA_TYPES:
        return CODE_EXTENSION_MEDIA_TYPES[lower_suffix]
    if lower_suffix in TEXT_EXTENSION_MEDIA_TYPES:
        return TEXT_EXTENSION_MEDIA_TYPES[lower_suffix]
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def is_code_media_type(media_type: str) -> bool:
    return media_type.startswith("text/x-code-")
