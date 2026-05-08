"""Wikipedia reader extension."""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from typing import Any

import certifi
from dorje_sdk import tool

API_URL = "https://en.wikipedia.org/w/api.php"
HTTP_TIMEOUT_S = 30.0
MAX_TITLE_CHARS = 200


@tool(description="Fetch a Wikipedia page by title and return Markdown text.")
def get_from_wikipedia(title: str) -> str:
    """Return a Wikipedia page as Markdown."""
    clean_title = _clean_title(title)
    page = _fetch_page(clean_title)
    return _to_markdown(page)


def _fetch_page(title: str) -> dict[str, Any]:
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|info",
        "explaintext": "1",
        "exsectionformat": "plain",
        "inprop": "url",
        "redirects": "1",
        "titles": title,
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "dorje-v0.2/0.1"})
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S, context=ssl_context) as response:
        payload = json.loads(response.read().decode("utf-8"))

    pages = payload.get("query", {}).get("pages", {})
    if not isinstance(pages, dict) or len(pages) == 0:
        raise RuntimeError("Wikipedia returned no pages")

    page = next(iter(pages.values()))
    if not isinstance(page, dict):
        raise RuntimeError("Wikipedia returned malformed page data")
    if "missing" in page:
        raise RuntimeError(f"Wikipedia page not found: {title}")
    return page


def _to_markdown(page: dict[str, Any]) -> str:
    title = str(page.get("title", "Untitled"))
    url = page.get("fullurl")
    extract = str(page.get("extract", "")).strip()

    lines = [f"# {title}", ""]
    if isinstance(url, str) and len(url) > 0:
        lines.extend([f"Source: {url}", ""])
    lines.append(extract)
    lines.append("")
    return "\n".join(lines)


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if len(cleaned) == 0:
        raise ValueError("title is empty")
    if len(cleaned) > MAX_TITLE_CHARS:
        raise ValueError("title is too long")
    return cleaned
