"""Markdown paragraph chunking extension."""

from __future__ import annotations

import uuid

from dorje.handles import HandleStore
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


@tool(description="Chunk a Markdown/plaintext handle or collection into paragraph-aligned chunk handles/collection.", produces="collection/full_text_chunk")
def chunk_md_handle(
    handle: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_paragraphs: int = DEFAULT_OVERLAP_PARAGRAPHS,
) -> dict[str, object] | list[dict[str, object]]:
    """Return paragraph-aligned chunk handles for Markdown/plaintext handle(s)."""
    store = HandleStore()
    record = store.get(handle)
    if record.kind == "collection":
        members: list[dict[str, object]] = []
        for member in record.members:
            member_handle = member.get("handle")
            if not isinstance(member_handle, str):
                continue
            member_record = store.get(member_handle)
            if member_record.content_type not in ("text/markdown", "text/plain"):
                continue
            members.extend(_chunk_one(store, member_record, max_chars=max_chars, overlap_paragraphs=overlap_paragraphs))
        collection = store.put_collection(
            members,
            label=f"{record.label or record.handle} chunks",
            metadata={"derived_from": record.handle, "chunker": "chunk_md_handle", "member_derivative_type": "full_text_chunk"},
            derivative_type="collection",
        )
        return {
            "source_handle": record.handle,
            "handle": collection.handle,
            "kind": collection.kind,
            "content_type": collection.content_type,
            "members_count": len(members),
            "members_preview": members[:20],
        }
    return _chunk_one(store, record, max_chars=max_chars, overlap_paragraphs=overlap_paragraphs)


def _chunk_one(
    store: HandleStore,
    record,
    max_chars: int,
    overlap_paragraphs: int,
) -> list[dict[str, object]]:
    if record.content_type not in ("text/markdown", "text/plain"):
        raise ValueError("chunk_md_handle only supports text/markdown or text/plain handles")
    chunks = chunk_md(record.content, max_chars=max_chars, overlap_paragraphs=overlap_paragraphs)
    output: list[dict[str, object]] = []
    for item in chunks:
        chunk_text = item["chunk"]
        if not isinstance(chunk_text, str):
            raise TypeError("chunk text must be a string")
        chunk_record = store.put(
            content=chunk_text,
            content_type=record.content_type,
            label=f"{record.label} chunk {len(output) + 1}",
            metadata={"derived_from": record.handle, "chunk_id": item["id"], "full_text": True},
            derivative_type="full_text_chunk",
        )
        output.append(
            {
                "id": item["id"],
                "source_handle": record.handle,
                "handle": chunk_record.handle,
                "kind": chunk_record.kind,
                "content_type": chunk_record.content_type,
                "role": chunk_record.role,
                "index_state": chunk_record.index_state,
                "derivative_type": chunk_record.derivative_type,
                "label": chunk_record.label,
                "start_paragraph": item["start_paragraph"],
                "end_paragraph": item["end_paragraph"],
                "char_count": item["char_count"],
                "preview": chunk_text[:500],
            }
        )
    return output


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
