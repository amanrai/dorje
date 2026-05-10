"""Shared chunker helpers."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from dorje.handles import HandleStore


@dataclass(frozen=True, slots=True)
class TextChunk:
    text: str
    chunk_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


Splitter = Callable[[str], list[TextChunk]]


def chunk_markdown_handle(
    handle: str,
    *,
    chunker_name: str,
    splitter: Splitter,
    label_suffix: str,
) -> dict[str, object]:
    store = HandleStore()
    record = store.get(handle)
    if record.kind == "collection":
        members: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        for member in record.members:
            member_handle = member.get("handle")
            if not isinstance(member_handle, str):
                skipped.append({"reason": "missing member handle", "member": member})
                continue
            member_record = store.get(member_handle)
            if not _is_markdown_like(member_record.content_type):
                skipped.append({"handle": member_record.handle, "content_type": member_record.content_type, "reason": "not markdown/plaintext"})
                continue
            members.extend(_chunk_one(store, member_record, chunker_name=chunker_name, splitter=splitter, label_suffix=label_suffix))
        collection = store.put_collection(
            members,
            label=f"{record.label or record.handle} {label_suffix}",
            metadata={"derived_from": record.handle, "chunker": chunker_name, "member_derivative_type": "full_text_chunk", "skipped": skipped},
            derivative_type="collection",
        )
        return _collection_result(record.handle, collection, members, skipped)
    if not _is_markdown_like(record.content_type):
        raise ValueError("Markdown chunkers require text/markdown or text/plain handles/collections")
    members = _chunk_one(store, record, chunker_name=chunker_name, splitter=splitter, label_suffix=label_suffix)
    collection = store.put_collection(
        members,
        label=f"{record.label or record.handle} {label_suffix}",
        metadata={"derived_from": record.handle, "chunker": chunker_name, "member_derivative_type": "full_text_chunk"},
        derivative_type="collection",
    )
    return _collection_result(record.handle, collection, members, [])


def full_text_chunks(text: str) -> list[TextChunk]:
    normalized = _normalize_text(text)
    return [TextChunk(text=normalized, chunk_type="text/full", metadata={"ordinal": 0})] if normalized else []


def section_chunks(text: str) -> list[TextChunk]:
    lines = _normalize_text(text).splitlines()
    sections: list[TextChunk] = []
    current: list[str] = []
    current_path: list[str] = []
    heading_stack: list[tuple[int, str]] = []
    start_line = 1
    for line_number, line in enumerate(lines, start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match and current:
            sections.append(
                TextChunk(
                    text="\n".join(current).strip() + "\n",
                    chunk_type="text/section",
                    metadata={"section_path": current_path, "start_line": start_line, "end_line": line_number - 1, "ordinal": len(sections)},
                )
            )
            current = []
            start_line = line_number
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack = [(lvl, name) for lvl, name in heading_stack if lvl < level]
            heading_stack.append((level, title))
            current_path = [name for _, name in heading_stack]
        current.append(line)
    if current:
        sections.append(
            TextChunk(
                text="\n".join(current).strip() + "\n",
                chunk_type="text/section",
                metadata={"section_path": current_path, "start_line": start_line, "end_line": len(lines), "ordinal": len(sections)},
            )
        )
    return [chunk for chunk in sections if chunk.text.strip()]


def paragraph_chunks(text: str, max_chars: int = 2_000) -> list[TextChunk]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", _normalize_text(text)) if part.strip()]
    chunks: list[TextChunk] = []
    current: list[str] = []
    start = 0
    for index, paragraph in enumerate(paragraphs):
        candidate = paragraph if not current else "\n\n".join([*current, paragraph])
        if current and len(candidate) > max_chars:
            body = "\n\n".join(current)
            chunks.append(TextChunk(text=body + "\n", chunk_type="text/paragraph", metadata={"start_paragraph": start, "end_paragraph": index - 1, "ordinal": len(chunks)}))
            current = [paragraph]
            start = index
        else:
            current.append(paragraph)
    if current:
        chunks.append(TextChunk(text="\n\n".join(current) + "\n", chunk_type="text/paragraph", metadata={"start_paragraph": start, "end_paragraph": len(paragraphs) - 1, "ordinal": len(chunks)}))
    return chunks


def sentence_chunks(text: str, max_chars: int = 1_200) -> list[TextChunk]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", _normalize_text(text).replace("\n", " ")) if part.strip()]
    chunks: list[TextChunk] = []
    current: list[str] = []
    start = 0
    for index, sentence in enumerate(sentences):
        candidate = sentence if not current else " ".join([*current, sentence])
        if current and len(candidate) > max_chars:
            body = " ".join(current)
            chunks.append(TextChunk(text=body + "\n", chunk_type="text/sentence", metadata={"start_sentence": start, "end_sentence": index - 1, "ordinal": len(chunks)}))
            current = [sentence]
            start = index
        else:
            current.append(sentence)
    if current:
        chunks.append(TextChunk(text=" ".join(current) + "\n", chunk_type="text/sentence", metadata={"start_sentence": start, "end_sentence": len(sentences) - 1, "ordinal": len(chunks)}))
    return chunks


def _chunk_one(store: HandleStore, record, *, chunker_name: str, splitter: Splitter, label_suffix: str) -> list[dict[str, object]]:
    chunks = splitter(record.content)
    members: list[dict[str, object]] = []
    for ordinal, chunk in enumerate(chunks):
        output = store.put(
            chunk.text,
            content_type=record.content_type,
            label=f"{record.label or record.handle} {label_suffix} {ordinal + 1}",
            index_state="indexable",
            metadata={
                "derived_from": record.handle,
                "chunker": chunker_name,
                "chunk_type": chunk.chunk_type,
                "source_media_type": record.content_type,
                **chunk.metadata,
            },
            derivative_type="full_text_chunk",
        )
        members.append(
            {
                "handle": output.handle,
                "kind": output.kind,
                "media_type": output.content_type,
                "content_type": output.content_type,
                "role": output.role,
                "index_state": output.index_state,
                "derivative_type": output.derivative_type,
                "label": output.label,
                "sha256": output.sha256,
                "metadata": output.metadata,
                "char_count": len(output.content),
                "preview": output.content[:500],
            }
        )
    return members


def _collection_result(source_handle: str, collection, members: list[dict[str, object]], skipped: list[dict[str, object]]) -> dict[str, object]:
    return {
        "source_handle": source_handle,
        "handle": collection.handle,
        "kind": collection.kind,
        "content_type": collection.content_type,
        "role": collection.role,
        "index_state": collection.index_state,
        "derivative_type": collection.derivative_type,
        "members_count": len(members),
        "skipped_count": len(skipped),
        "members_preview": members[:20],
    }


def _is_markdown_like(content_type: str) -> bool:
    return content_type in ("text/markdown", "text/plain")


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n" if text.strip() else ""
