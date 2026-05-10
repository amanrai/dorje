"""Collection handle inspection and filtering tools."""

from __future__ import annotations

from collections import Counter
from fnmatch import fnmatch
from typing import Any

from dorje.handles import HandleStore
from dorje_sdk import tool

DEFAULT_SAMPLE_SIZE = 20
MAX_SAMPLE_SIZE = 200


@tool(description="Inspect a collection handle with bounded samples and counts by handle axes.")
def inspect_collection(handle: str, sample_size: int = DEFAULT_SAMPLE_SIZE) -> dict[str, object]:
    """Return summary statistics for a collection handle without expanding all content."""
    if sample_size < 0 or sample_size > MAX_SAMPLE_SIZE:
        raise ValueError(f"sample_size must be between 0 and {MAX_SAMPLE_SIZE}")
    store = HandleStore()
    record = store.get(handle)
    if record.kind != "collection":
        raise ValueError("inspect_collection requires a collection handle")
    members = list(record.members)
    return {
        "handle": record.handle,
        "kind": record.kind,
        "content_type": record.content_type,
        "role": record.role,
        "index_state": record.index_state,
        "derivative_type": record.derivative_type,
        "label": record.label,
        "members_count": len(members),
        "by_kind": _counts(members, "kind"),
        "by_media_type": _counts(members, "media_type", fallback_key="content_type"),
        "by_role": _counts(members, "role"),
        "by_index_state": _counts(members, "index_state"),
        "by_derivative_type": _counts(members, "derivative_type"),
        "sample": members[:sample_size],
    }


@tool(description="Filter a collection handle by handle axes, media type, derivative type, and path/label glob.", produces="collection")
def filter_collection(
    handle: str,
    kind: str | None = None,
    media_type: str | None = None,
    role: str | None = None,
    index_state: str | None = None,
    derivative_type: str | None = None,
    path_glob: str | None = None,
    label_glob: str | None = None,
    max_results: int | None = None,
) -> dict[str, object]:
    """Return a new collection containing members that match all supplied filters."""
    if max_results is not None and max_results <= 0:
        raise ValueError("max_results must be positive")
    store = HandleStore()
    record = store.get(handle)
    if record.kind != "collection":
        raise ValueError("filter_collection requires a collection handle")

    members: list[dict[str, Any]] = []
    skipped = 0
    for member in record.members:
        if _matches(
            member,
            kind=kind,
            media_type=media_type,
            role=role,
            index_state=index_state,
            derivative_type=derivative_type,
            path_glob=path_glob,
            label_glob=label_glob,
        ):
            if max_results is not None and len(members) >= max_results:
                skipped += 1
                continue
            members.append(dict(member))
        else:
            skipped += 1

    collection = store.put_collection(
        members,
        label=f"filtered {record.label or record.handle}",
        metadata={
            "derived_from": record.handle,
            "filter": {
                "kind": kind,
                "media_type": media_type,
                "role": role,
                "index_state": index_state,
                "derivative_type": derivative_type,
                "path_glob": path_glob,
                "label_glob": label_glob,
                "max_results": max_results,
            },
            "input_members_count": len(record.members),
            "skipped_count": skipped,
        },
        derivative_type="collection",
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
        "skipped_count": skipped,
        "members_preview": members[:DEFAULT_SAMPLE_SIZE],
    }


def _counts(members: list[dict[str, Any]], key: str, fallback_key: str | None = None) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for member in members:
        value = member.get(key)
        if not isinstance(value, str) and fallback_key is not None:
            value = member.get(fallback_key)
        counter[str(value) if isinstance(value, str) and value else "<missing>"] += 1
    return dict(sorted(counter.items()))


def _matches(
    member: dict[str, Any],
    *,
    kind: str | None,
    media_type: str | None,
    role: str | None,
    index_state: str | None,
    derivative_type: str | None,
    path_glob: str | None,
    label_glob: str | None,
) -> bool:
    return (
        _eq(member.get("kind"), kind)
        and _eq(member.get("media_type", member.get("content_type")), media_type)
        and _eq(member.get("role"), role)
        and _eq(member.get("index_state"), index_state)
        and _eq(member.get("derivative_type"), derivative_type)
        and _glob(member.get("path"), path_glob)
        and _glob(member.get("label"), label_glob)
    )


def _eq(value: object, expected: str | None) -> bool:
    return expected is None or value == expected


def _glob(value: object, pattern: str | None) -> bool:
    if pattern is None:
        return True
    return isinstance(value, str) and fnmatch(value, pattern)
