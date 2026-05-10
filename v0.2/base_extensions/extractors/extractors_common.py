"""Shared helpers for extractor tools."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
import urllib.request

from dorje.handles import HandleStore

DEFAULT_PREVIEW_CHARS = 1000
HTML_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}
PYTHON_MEDIA_TYPES = {"text/x-code-python", "text/x-python", "text/plain", "application/octet-stream"}
JAVASCRIPT_MEDIA_TYPES = {"text/x-code-javascript", "text/x-code-jsx", "text/x-code-typescript", "text/x-code-tsx", "text/plain", "application/octet-stream"}
CSS_MEDIA_TYPES = {"text/x-code-css", "text/x-code-scss", "text/x-code-sass", "text/x-code-less", "text/plain", "application/octet-stream"}


def get_file_ref(store: HandleStore, handle: str):
    record = store.get(handle)
    if record.kind != "file_ref":
        raise ValueError("extractors require a file_ref handle")
    return record


def member(output) -> dict[str, object]:
    return {
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
    }


def collection_result(source_handle: str, collection, members: list[dict[str, Any]]) -> dict[str, object]:
    return {
        "source_handle": source_handle,
        "handle": collection.handle,
        "kind": collection.kind,
        "content_type": collection.content_type,
        "role": collection.role,
        "index_state": collection.index_state,
        "derivative_type": collection.derivative_type,
        "members_count": len(members),
        "members_preview": members[:20],
    }


def handle_result(source_handle: str, output) -> dict[str, object]:
    return {
        "source_handle": source_handle,
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


def resolve_image_src(src: str, base_url: str, file_path: str | None) -> str:
    parsed = urlparse(src)
    if parsed.scheme in ("http", "https", "file", "data"):
        return src
    if base_url:
        return urljoin(base_url, src)
    if file_path:
        return Path(file_path).resolve().parent.joinpath(unquote(src)).as_uri()
    return src


def fetch_image_bytes(src: str, max_bytes: int) -> tuple[bytes, str]:
    parsed = urlparse(src)
    if parsed.scheme == "data":
        header, _, payload = src.partition(",")
        media_type = header.removeprefix("data:").split(";", 1)[0] or "application/octet-stream"
        data = base64.b64decode(payload) if ";base64" in header else unquote(payload).encode()
    elif parsed.scheme == "file":
        path = Path(unquote(parsed.path))
        data = path.read_bytes()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    elif parsed.scheme in ("http", "https"):
        with urllib.request.urlopen(src, timeout=30) as response:  # noqa: S310 - local trusted exploratory tool
            data = response.read(max_bytes + 1)
            media_type = response.headers.get_content_type() or mimetypes.guess_type(src)[0] or "application/octet-stream"
    else:
        path = Path(src)
        data = path.read_bytes()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if len(data) > max_bytes:
        raise ValueError(f"image exceeds max_bytes={max_bytes}")
    return data, media_type
