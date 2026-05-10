"""Prepare FTS-compatible full-text handles."""

from __future__ import annotations

from typing import Any

from dorje.handles import HandleStore
from dorje_sdk import tool

FTS_MEDIA_TYPES = {"text/plain", "text/markdown"}
DEFAULT_PREVIEW_CHARS = 1000


@tool(description="Create FTS-compatible full-text derivative handle(s) from indexable text handle(s).", produces="fts_full_text_collection/fts_full_text")
def get_fts_compatible_handle(handle: str, label: str = "") -> dict[str, object]:
    """Return full-text derivative handle(s) suitable for insertion into SQLite FTS.

    This does not write to SQLite yet. It materializes normalized full text as a
    derivative handle so a later FTS indexer can insert exactly that text.
    """
    store = HandleStore()
    record = store.get(handle)
    if record.kind == "collection":
        members: list[dict[str, Any]] = []
        skipped: list[dict[str, object]] = []
        for member in record.members:
            member_handle = member.get("handle")
            if not isinstance(member_handle, str):
                skipped.append({"reason": "missing member handle", "member": member})
                continue
            member_record = store.get(member_handle)
            if not _is_fts_compatible(member_record.content_type, member_record.index_state):
                skipped.append(
                    {
                        "handle": member_record.handle,
                        "content_type": member_record.content_type,
                        "index_state": member_record.index_state,
                        "reason": "not fts compatible",
                    }
                )
                continue
            members.append(_materialize_one(store, member_record, label=""))
        collection = store.put_collection(
            members,
            label=label or f"{record.label or record.handle} fts full text collection",
            metadata={
                "derived_from": record.handle,
                "preparer": "get_fts_compatible_handle",
                "skipped": skipped,
            },
            derivative_type="fts_full_text_collection",
        )
        return {
            "source_handle": record.handle,
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
    if not _is_fts_compatible(record.content_type, record.index_state):
        raise ValueError("get_fts_compatible_handle requires text/plain or text/markdown handles with index_state=indexable")
    return _materialize_one(store, record, label=label)


def _materialize_one(store: HandleStore, record, label: str) -> dict[str, object]:
    full_text = _normalize_full_text(record.content)
    output = store.put(
        content=full_text,
        content_type="text/plain",
        label=label or f"{record.label or record.handle} fts full text",
        index_state="indexable",
        metadata={
            "derived_from": record.handle,
            "preparer": "get_fts_compatible_handle",
            "source_content_type": record.content_type,
        },
        derivative_type="fts_full_text",
    )
    return {
        "source_handle": record.handle,
        "handle": output.handle,
        "kind": output.kind,
        "content_type": output.content_type,
        "role": output.role,
        "index_state": output.index_state,
        "derivative_type": output.derivative_type,
        "label": output.label,
        "sha256": output.sha256,
        "char_count": len(output.content),
        "preview": output.content[:DEFAULT_PREVIEW_CHARS],
    }


def _is_fts_compatible(content_type: str, index_state: str) -> bool:
    return index_state == "indexable" and content_type in FTS_MEDIA_TYPES


def _normalize_full_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip() + "\n"
