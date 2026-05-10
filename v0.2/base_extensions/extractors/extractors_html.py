"""HTML extractors."""

from __future__ import annotations

import base64
import re
from typing import Any

import orjson
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify

from dorje.handles import HandleStore
from dorje_sdk import tool
from extractors_common import HTML_MEDIA_TYPES, collection_result, fetch_image_bytes, get_file_ref, handle_result, member, resolve_image_src


@tool(description="Extract Markdown from a text/html or application/xhtml+xml file_ref handle.", requires="file_ref:text/html|application/xhtml+xml", produces="extracted_markdown")
def extract_html_to_markdown(handle: str, label: str = "") -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type not in HTML_MEDIA_TYPES:
        raise ValueError("extract_html_to_markdown requires a text/html or application/xhtml+xml file_ref handle")
    soup = BeautifulSoup(record.content, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    output = store.put(
        markdownify(str(soup), heading_style="ATX", bullets="-").strip() + "\n",
        content_type="text/markdown",
        label=label or f"{record.label or record.handle} extracted markdown",
        index_state="indexable",
        metadata={"derived_from": record.handle, "extractor": "extract_html_to_markdown", "source_media_type": record.content_type},
        derivative_type="extracted_markdown",
    )
    return handle_result(record.handle, output)


@tool(description="Extract Markdown table derivatives from a text/html or application/xhtml+xml file_ref handle.", requires="file_ref:text/html|application/xhtml+xml", produces="collection/table")
def extract_tables_from_html(handle: str, label: str = "") -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type not in HTML_MEDIA_TYPES:
        raise ValueError("extract_tables_from_html requires a text/html or application/xhtml+xml file_ref handle")
    soup = BeautifulSoup(record.content, "html.parser")
    members: list[dict[str, Any]] = []
    for index, table in enumerate(soup.find_all("table"), start=1):
        if not isinstance(table, Tag):
            continue
        caption_tag = table.find("caption")
        caption = caption_tag.get_text(" ", strip=True) if isinstance(caption_tag, Tag) else ""
        table_html = str(table)
        table_markdown = markdownify(table_html, heading_style="ATX", bullets="-").strip() + "\n"
        payload = _table_payload(table, table_index=index, caption=caption, markdown=table_markdown, html=table_html)
        output = store.put(
            orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode(),
            content_type="application/vnd.dorje.table+json",
            label=f"{label or record.label or record.handle}::table_{index}",
            index_state="indexable",
            metadata={"derived_from": record.handle, "extractor": "extract_tables_from_html", "source_media_type": record.content_type, "table_index": index, "caption": caption, "payload_schema": "dorje.table.v1"},
            derivative_type="table",
        )
        members.append(member(output))
    collection = store.put_collection(members, label=label or f"{record.label or record.handle} html tables", metadata={"derived_from": record.handle, "extractor": "extract_tables_from_html", "member_derivative_type": "table"}, derivative_type="collection")
    return collection_result(record.handle, collection, members)


def _table_payload(table: Tag, table_index: int, caption: str, markdown: str, html: str) -> dict[str, object]:
    matrix = _table_matrix(table)
    header = matrix[0] if matrix else []
    data_rows = matrix[1:] if len(matrix) > 1 else []
    columns = [
        {"index": idx, "name": name, "type": _infer_column_type([row[idx] if idx < len(row) else "" for row in data_rows])}
        for idx, name in enumerate(header)
    ]
    rows = [{str(idx): _coerce_value(value, columns[idx]["type"] if idx < len(columns) else "string") for idx, value in enumerate(row)} for row in data_rows]
    return {
        "schema": "dorje.table.v1",
        "table_index": table_index,
        "caption": caption,
        "columns": columns,
        "rows": rows,
        "rows_raw": data_rows,
        "markdown": markdown,
        "source": {"format": "html", "html": html},
    }


def _table_matrix(table: Tag) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        if not isinstance(tr, Tag):
            continue
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"], recursive=False) if isinstance(cell, Tag)]
        if cells:
            rows.append(cells)
    return rows


def _infer_column_type(values: list[str]) -> str:
    non_empty = [value.strip() for value in values if value.strip()]
    if not non_empty:
        return "string"
    if all(re.fullmatch(r"[-+]?\d+", value.replace(",", "")) for value in non_empty):
        return "integer"
    if all(_looks_float(value) for value in non_empty):
        return "float"
    if all(value.lower() in ("true", "false", "yes", "no") for value in non_empty):
        return "boolean"
    return "string"


def _looks_float(value: str) -> bool:
    normalized = value.replace(",", "")
    return re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", normalized) is not None


def _coerce_value(value: str, column_type: object) -> object:
    if not isinstance(column_type, str):
        return value
    stripped = value.strip()
    if stripped == "":
        return None
    if column_type == "integer":
        return int(stripped.replace(",", ""))
    if column_type == "float":
        return float(stripped.replace(",", ""))
    if column_type == "boolean":
        return stripped.lower() in ("true", "yes")
    return value


@tool(description="Fetch actual image payloads referenced by HTML img tags and store each as base64 image JSON.", requires="file_ref:text/html|application/xhtml+xml", produces="collection/image")
def get_images_for_html(handle: str, base_url: str = "", label: str = "", max_bytes: int = 10_000_000) -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type not in HTML_MEDIA_TYPES:
        raise ValueError("get_images_for_html requires a text/html or application/xhtml+xml file_ref handle")
    soup = BeautifulSoup(record.content, "html.parser")
    members: list[dict[str, Any]] = []
    for index, img in enumerate([tag for tag in soup.find_all("img") if isinstance(tag, Tag)], start=1):
        src = str(img.get("src") or "")
        if not src:
            continue
        resolved_src = resolve_image_src(src, base_url, record.path)
        image_bytes, media_type = fetch_image_bytes(resolved_src, max_bytes=max_bytes)
        alt = str(img.get("alt") or "")
        payload = {"src": src, "resolved_src": resolved_src, "media_type": media_type, "base64": base64.b64encode(image_bytes).decode("ascii"), "alt": alt, "byte_count": len(image_bytes)}
        output = store.put(
            orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode(),
            content_type="application/vnd.dorje.image+json",
            label=f"{label or record.label or record.handle}::image_{index}",
            index_state="metadata",
            metadata={"derived_from": record.handle, "extractor": "get_images_for_html", "source_media_type": record.content_type, "image_index": index, "src": src, "resolved_src": resolved_src, "image_media_type": media_type, "alt": alt, "byte_count": len(image_bytes)},
            derivative_type="image",
        )
        members.append(member(output))
    collection = store.put_collection(members, label=label or f"{record.label or record.handle} html images", metadata={"derived_from": record.handle, "extractor": "get_images_for_html", "member_derivative_type": "image"}, derivative_type="collection")
    return collection_result(record.handle, collection, members)


@tool(description="Extract document figure records from HTML img/figure elements: src, alt text, caption, and Markdown reference; does not fetch image bytes.", requires="file_ref:text/html|application/xhtml+xml", produces="collection/figure")
def extract_figures_from_html(handle: str, label: str = "") -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type not in HTML_MEDIA_TYPES:
        raise ValueError("extract_figures_from_html requires a text/html or application/xhtml+xml file_ref handle")
    soup = BeautifulSoup(record.content, "html.parser")
    members: list[dict[str, Any]] = []
    for index, img in enumerate([tag for tag in soup.find_all("img") if isinstance(tag, Tag)], start=1):
        src = str(img.get("src") or "")
        alt = str(img.get("alt") or "")
        figure = img.find_parent("figure")
        caption_tag = figure.find("figcaption") if isinstance(figure, Tag) else None
        caption = caption_tag.get_text(" ", strip=True) if isinstance(caption_tag, Tag) else ""
        figure_markdown = f"![{alt}]({src})\n\n{caption}\n".strip() + "\n"
        payload = {"figure_index": index, "src": src, "alt": alt, "caption": caption, "markdown": figure_markdown}
        output = store.put(
            orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode(),
            content_type="application/vnd.dorje.figure+json",
            label=f"{label or record.label or record.handle}::figure_{index}",
            index_state="indexable",
            metadata={"derived_from": record.handle, "extractor": "extract_figures_from_html", "source_media_type": record.content_type, "figure_index": index, "src": src, "alt": alt, "caption": caption, "payload_schema": "dorje.figure.v1"},
            derivative_type="figure",
        )
        members.append(member(output))
    collection = store.put_collection(members, label=label or f"{record.label or record.handle} html figures", metadata={"derived_from": record.handle, "extractor": "extract_figures_from_html", "member_derivative_type": "figure"}, derivative_type="collection")
    return collection_result(record.handle, collection, members)
