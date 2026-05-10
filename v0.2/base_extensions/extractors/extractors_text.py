"""Plain text and Markdown extractors."""

from __future__ import annotations

import re
from typing import Any

import orjson

from dorje.handles import HandleStore
from dorje_sdk import tool
from extractors_common import collection_result, get_file_ref, handle_result, member


@tool(description="Extract Markdown from a text/plain file_ref handle by treating plaintext as indexable Markdown text.")
def extract_plaintext_to_markdown(handle: str, label: str = "") -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type != "text/plain":
        raise ValueError("extract_plaintext_to_markdown requires a text/plain file_ref handle")
    output = store.put(
        record.content.strip() + "\n",
        content_type="text/markdown",
        label=label or f"{record.label or record.handle} plaintext markdown",
        index_state="indexable",
        metadata={"derived_from": record.handle, "extractor": "extract_plaintext_to_markdown", "source_media_type": record.content_type},
        derivative_type="extracted_markdown",
    )
    return handle_result(record.handle, output)


@tool(description="Extract indexable Markdown from a text/markdown file_ref handle without changing representation.")
def extract_markdown_source(handle: str, label: str = "") -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type != "text/markdown":
        raise ValueError("extract_markdown_source requires a text/markdown file_ref handle")
    output = store.put(
        record.content,
        content_type="text/markdown",
        label=label or f"{record.label or record.handle} markdown source copy",
        index_state="indexable",
        metadata={"derived_from": record.handle, "extractor": "extract_markdown_source", "source_media_type": record.content_type},
        derivative_type="extracted_markdown",
    )
    return handle_result(record.handle, output)


@tool(description="Extract bibliography/reference entries from a Markdown/plaintext paper file_ref handle.")
def extract_references_from_paper(handle: str, label: str = "") -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type not in ("text/markdown", "text/plain"):
        raise ValueError("extract_references_from_paper currently requires text/markdown or text/plain")
    references = _reference_entries(record.content)
    members: list[dict[str, Any]] = []
    for index, ref in enumerate(references, start=1):
        reference_text = ref.strip() + "\n"
        payload = {"reference_index": index, "text": reference_text}
        output = store.put(
            orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode(),
            content_type="application/vnd.dorje.reference+json",
            label=f"{label or record.label or record.handle}::reference_{index}",
            index_state="indexable",
            metadata={"derived_from": record.handle, "extractor": "extract_references_from_paper", "source_media_type": record.content_type, "reference_index": index, "payload_schema": "dorje.reference.v1"},
            derivative_type="reference",
        )
        members.append(member(output))
    collection = store.put_collection(members, label=label or f"{record.label or record.handle} references", metadata={"derived_from": record.handle, "extractor": "extract_references_from_paper"}, derivative_type="reference_collection")
    return collection_result(record.handle, collection, members)


def _reference_entries(content: str) -> list[str]:
    lines = content.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if re.match(r"^\s*#{1,6}\s*(references|bibliography)\s*$", line, flags=re.IGNORECASE) or re.match(r"^\s*(references|bibliography)\s*$", line, flags=re.IGNORECASE):
            start = idx + 1
            break
    if start is None:
        return []
    section: list[str] = []
    for line in lines[start:]:
        if re.match(r"^\s*#{1,6}\s+", line):
            break
        section.append(line)
    entries: list[str] = []
    current: list[str] = []
    for line in section:
        if re.match(r"^\s*(?:[-*]|\[?\d+\]?\.?|\d+\))\s+", line) and current:
            entries.append("\n".join(current).strip())
            current = [line]
        elif line.strip():
            current.append(line)
    if current:
        entries.append("\n".join(current).strip())
    return [entry for entry in entries if entry]
