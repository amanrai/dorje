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


@tool(description="Convert an HTML handle into a Markdown handle.")
def html_handle_to_md_handle(handle: str, strip_scripts: bool = True, label: str = "") -> dict[str, object]:
    """Read an HTML handle, convert it to Markdown, and store the Markdown as a new handle."""
    store = HandleStore()
    record = store.get(handle)
    if record.content_type not in ("text/html", "application/xhtml+xml", "text/plain"):
        raise ValueError("html_handle_to_md_handle only supports text/html, application/xhtml+xml, or text/plain handles")
    markdown = _convert(record.content, strip_scripts=strip_scripts)
    output = store.put(
        content=markdown,
        content_type="text/markdown",
        label=label or f"{record.label or record.handle} markdown",
    )
    return {
        "source_handle": record.handle,
        "handle": output.handle,
        "content_type": output.content_type,
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
