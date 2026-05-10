from pathlib import Path
from typing import Any, cast

from dorje.extensions import load_extensions
from dorje.handles import HandleStore


def test_get_fts_compatible_handle_from_markdown_handle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = HandleStore()
    source = store.put("# Title\n\nBody", content_type="text/markdown", label="doc", derivative_type="markdown_conversion")
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    result = cast(dict[str, Any], registry.call("get_fts_compatible_handle", {"handle": source.handle}))

    assert result["kind"] == "derivative"
    assert result["content_type"] == "text/plain"
    assert result["derivative_type"] == "fts_full_text"
    output = store.get(cast(str, result["handle"]))
    assert output.content == "# Title\n\nBody\n"
    assert output.metadata["derived_from"] == source.handle


def test_get_fts_compatible_handle_from_collection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = HandleStore()
    md = store.put("# A", content_type="text/markdown", label="a", derivative_type="chunk")
    html = store.put("<h1>B</h1>", content_type="text/html", label="b", derivative_type="html_raw")
    collection = store.put_collection(
        [
            {"handle": md.handle, "kind": md.kind, "media_type": md.content_type, "content_type": md.content_type, "index_state": md.index_state},
            {"handle": html.handle, "kind": html.kind, "media_type": html.content_type, "content_type": html.content_type, "index_state": html.index_state},
        ],
        derivative_type="mixed_collection",
    )
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    result = cast(dict[str, Any], registry.call("get_fts_compatible_handle", {"handle": collection.handle}))

    assert result["kind"] == "collection"
    assert result["derivative_type"] == "fts_full_text_collection"
    assert result["members_count"] == 1
    assert result["skipped_count"] == 1
