"""Markdown paragraph chunking extension."""

from __future__ import annotations

import uuid

from dorje_sdk import tool

DEFAULT_MAX_CHARS = 2000
DEFAULT_OVERLAP_PARAGRAPHS = 0
MAX_INPUT_CHARS = 2_000_000


@tool(description="Chunk Markdown text into paragraph-aligned chunks with UUIDs.")
def chunk_md(
    markdown: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_paragraphs: int = DEFAULT_OVERLAP_PARAGRAPHS,
) -> list[dict[str, object]]:
    """Return paragraph-aligned Markdown chunks."""
    _validate(markdown, max_chars, overlap_paragraphs)
    paragraphs = _split_paragraphs(markdown)
    chunks: list[dict[str, object]] = []
    index = 0

    while index < len(paragraphs):
        start = index
        current: list[str] = []
        current_chars = 0

        while index < len(paragraphs):
            paragraph = paragraphs[index]
            added_chars = len(paragraph) if len(current) == 0 else len(paragraph) + 2
            if len(current) > 0 and current_chars + added_chars > max_chars:
                break
            current.append(paragraph)
            current_chars += added_chars
            index += 1
            if current_chars >= max_chars:
                break

        if len(current) == 0:
            current.append(paragraphs[index])
            index += 1

        end = index
        text = "\n\n".join(current)
        chunks.append(
            {
                "id": str(uuid.uuid4()),
                "chunk": text,
                "start_paragraph": start,
                "end_paragraph": end - 1,
                "char_count": len(text),
            }
        )

        if overlap_paragraphs > 0 and index < len(paragraphs):
            index = max(start + 1, index - overlap_paragraphs)

    return chunks


def _validate(markdown: str, max_chars: int, overlap_paragraphs: int) -> None:
    if not isinstance(markdown, str):
        raise TypeError("markdown must be a string")
    if len(markdown) > MAX_INPUT_CHARS:
        raise ValueError("markdown is too large")
    if not isinstance(max_chars, int):
        raise TypeError("max_chars must be an integer")
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not isinstance(overlap_paragraphs, int):
        raise TypeError("overlap_paragraphs must be an integer")
    if overlap_paragraphs < 0:
        raise ValueError("overlap_paragraphs must be non-negative")


def _split_paragraphs(markdown: str) -> list[str]:
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    raw = normalized.split("\n\n")
    paragraphs = [part.strip() for part in raw if len(part.strip()) > 0]
    if len(paragraphs) == 0:
        return [""]
    return paragraphs
