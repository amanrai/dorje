#!/usr/bin/env python3
"""Fetch a Wikipedia page into local wiki_data files."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import certifi

API_URL = "https://en.wikipedia.org/w/api.php"
MAX_TITLE_CHARS = 200
HTTP_TIMEOUT_S = 30.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a Wikipedia page into wiki_data/.")
    parser.add_argument("title", help="Wikipedia page title, e.g. 'SQLite'")
    parser.add_argument(
        "--out-dir",
        default="wiki_data",
        help="Output directory. Default: wiki_data",
    )
    args = parser.parse_args()

    title = _clean_title(args.title)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    page = fetch_page(title)
    slug = _slug(page["title"])

    json_path = out_dir / f"{slug}.json"
    text_path = out_dir / f"{slug}.txt"

    json_path.write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
    text_path.write_text(str(page["extract"]), encoding="utf-8")

    print(f"wrote {json_path}")
    print(f"wrote {text_path}")
    return 0


def fetch_page(title: str) -> dict[str, Any]:
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

    return {
        "pageid": page.get("pageid"),
        "title": page.get("title", title),
        "url": page.get("fullurl"),
        "extract": page.get("extract", ""),
    }


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if len(cleaned) == 0:
        raise ValueError("title is empty")
    if len(cleaned) > MAX_TITLE_CHARS:
        raise ValueError("title is too long")
    return cleaned


def _slug(title: str) -> str:
    lowered = title.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered)
    slug = slug.strip("_")
    if len(slug) == 0:
        return "page"
    return slug


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
