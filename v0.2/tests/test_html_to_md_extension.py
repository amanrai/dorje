from pathlib import Path
from typing import Any, cast

from dorje.extensions import load_extensions
from dorje.handles import HandleStore


def test_html_to_md_converts_inline_html() -> None:
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    result = cast(dict[str, Any], registry.call("html_to_md", {"html": "<h1>Hello</h1><p>World</p><script>bad()</script>"}))

    assert result["content_type"] == "text/markdown"
    assert "# Hello" in result["markdown"]
    assert "World" in result["markdown"]
    assert "bad()" not in result["markdown"]


def test_html_handle_to_md_handle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = HandleStore().put(content="<h2>Section</h2><p>Text</p>", content_type="text/html", label="source html")
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    result = cast(dict[str, Any], registry.call("html_handle_to_md_handle", {"handle": source.handle}))

    assert result["content_type"] == "text/markdown"
    output = HandleStore().get(cast(str, result["handle"]))
    assert output.content_type == "text/markdown"
    assert "## Section" in output.content
    assert "Text" in output.content
