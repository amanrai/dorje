"""List filesystem paths as file-ref handles."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from dorje.handles import HandleStore
from dorje_sdk import tool

DEFAULT_MAX_RESULTS = 1000
MAX_RESULTS_LIMIT = 10000


@tool(description="List files as uncopied file-ref source handles and return a collection handle.")
def ls_as_handles(
    path: str = ".",
    glob: str = "*",
    recursive: bool = False,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict[str, object]:
    """Create file-ref handles for matched files and return a collection handle."""
    if max_results <= 0 or max_results > MAX_RESULTS_LIMIT:
        raise ValueError(f"max_results must be between 1 and {MAX_RESULTS_LIMIT}")
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("path must be an existing directory")

    pattern = f"**/{glob}" if recursive else glob
    files = [item for item in sorted(root.glob(pattern)) if item.is_file()]
    limited = files[:max_results]
    store = HandleStore()
    members: list[dict[str, Any]] = []
    for file_path in limited:
        media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        record = store.put_file_ref(
            file_path,
            content_type=media_type,
            label=str(file_path.relative_to(root)),
            metadata={"extension": file_path.suffix.lower(), "root": str(root)},
        )
        members.append(
            {
                "handle": record.handle,
                "kind": record.kind,
                "media_type": record.content_type,
                "content_type": record.content_type,
                "role": record.role,
                "index_state": record.index_state,
                "label": record.label,
                "path": record.path,
                "size_bytes": file_path.stat().st_size,
                "sha256": record.sha256,
                "metadata": record.metadata,
            }
        )

    collection = store.put_collection(
        members,
        label=f"ls_as_handles {root} {glob}",
        metadata={
            "path": str(root),
            "glob": glob,
            "recursive": recursive,
            "matched_count": len(files),
            "returned_count": len(members),
            "truncated": len(files) > len(members),
        },
        derivative_type="file_ref_collection",
    )
    return {
        "handle": collection.handle,
        "kind": collection.kind,
        "media_type": collection.content_type,
        "content_type": collection.content_type,
        "role": collection.role,
        "index_state": collection.index_state,
        "label": collection.label,
        "members_count": len(members),
        "matched_count": len(files),
        "truncated": len(files) > len(members),
        "members_preview": members[:20],
    }
