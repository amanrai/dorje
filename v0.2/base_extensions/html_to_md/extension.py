"""HTML to Markdown conversion extension."""

from __future__ import annotations

from bs4 import BeautifulSoup
from markdownify import markdownify as md

from dorje.handles import HandleStore
from dorje_sdk import tool

MAX_HTML_CHARS = 5_000_000
DEFAULT_PREVIEW_CHARS = 1000


@tool(description="Convert an HTML string to Markdown text.")
def html_to_md(html: str, strip_scripts: bool = True) -> dict[str, object]:
    """Convert HTML text to Markdown and return Markdown inline."""
    markdown = _convert(html, strip_scripts=strip_scripts)
    return {
        "content_type": "text/markdown",
        "char_count": len(markdown),
        "preview": markdown[:DEFAULT_PREVIEW_CHARS],
        "markdown": markdown,
    }


@tool(description="Convert an HTML handle or collection of HTML handles into Markdown handle(s).")
def html_handle_to_md_handle(handle: str, strip_scripts: bool = True, label: str = "") -> dict[str, object]:
    """Read HTML handle(s), convert to Markdown, and store Markdown handle(s)."""
    store = HandleStore()
    record = store.get(handle)
    if record.kind == "collection":
        members = []
        for member in record.members:
            member_handle = member.get("handle")
            if not isinstance(member_handle, str):
                continue
            member_record = store.get(member_handle)
            if member_record.content_type not in ("text/html", "application/xhtml+xml", "text/plain"):
                continue
            members.append(_convert_one(store, member_record, strip_scripts=strip_scripts, label=""))
        collection = store.put_collection(
            members,
            label=label or f"{record.label or record.handle} markdown collection",
            metadata={"derived_from": record.handle, "converter": "html_handle_to_md_handle"},
            derivative_type="markdown_conversion_collection",
        )
        return {
            "source_handle": record.handle,
            "handle": collection.handle,
            "kind": collection.kind,
            "content_type": collection.content_type,
            "members_count": len(members),
            "members_preview": members[:20],
        }
    return _convert_one(store, record, strip_scripts=strip_scripts, label=label)


def _convert_one(store: HandleStore, record, strip_scripts: bool, label: str) -> dict[str, object]:
    if record.content_type not in ("text/html", "application/xhtml+xml", "text/plain"):
        raise ValueError("html_handle_to_md_handle only supports text/html, application/xhtml+xml, or text/plain handles")
    markdown = _convert(record.content, strip_scripts=strip_scripts)
    output = store.put(
        content=markdown,
        content_type="text/markdown",
        label=label or f"{record.label or record.handle} markdown",
        metadata={"derived_from": record.handle, "converter": "html_handle_to_md_handle"},
        derivative_type="markdown_conversion",
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


def _convert(html: str, strip_scripts: bool = True) -> str:
    if not isinstance(html, str):
        raise TypeError("html must be a string")
    if len(html) > MAX_HTML_CHARS:
        raise ValueError("html is too large")

    source = html
    if strip_scripts:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        source = str(soup)

    markdown = md(
        source,
        heading_style="ATX",
        bullets="-",
        strip=["script", "style", "noscript", "template"],
    )
    return _tidy(markdown)


def _tidy(markdown: str) -> str:
    # Collapse very large blank runs while preserving Markdown paragraph breaks.
    lines = [line.rstrip() for line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out: list[str] = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                out.append("")
        else:
            blank_count = 0
            out.append(line)
    return "\n".join(out).strip() + "\n"
