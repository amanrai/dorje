from pathlib import Path
from typing import Any, cast

from dorje.extensions import load_extensions
from dorje.handles import HandleStore


def test_ls_as_handles_returns_collection_of_file_refs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.html").write_text("<h1>A</h1>", encoding="utf-8")
    (data / "b.txt").write_text("B", encoding="utf-8")
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    result = cast(dict[str, Any], registry.call("ls_as_handles", {"path": str(data), "glob": "*.html"}))

    assert result["kind"] == "collection"
    assert result["members_count"] == 1
    collection = HandleStore().get(cast(str, result["handle"]))
    assert collection.kind == "collection"
    assert len(collection.members) == 1
    member = collection.members[0]
    assert member["kind"] == "file_ref"
    assert member["media_type"] == "text/html"
    file_ref = HandleStore().get(cast(str, member["handle"]))
    assert file_ref.kind == "file_ref"
    assert file_ref.content == "<h1>A</h1>"


def test_html_and_chunk_tools_accept_collections(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.html").write_text("<h1>A</h1><p>Alpha</p>", encoding="utf-8")
    (data / "b.html").write_text("<h1>B</h1><p>Beta</p>", encoding="utf-8")
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    source_collection = cast(dict[str, Any], registry.call("ls_as_handles", {"path": str(data), "glob": "*.html"}))
    md_collection = cast(dict[str, Any], registry.call("html_handle_to_md_handle", {"handle": source_collection["handle"]}))
    chunk_collection = cast(dict[str, Any], registry.call("chunk_md_handle", {"handle": md_collection["handle"], "max_chars": 100}))

    assert md_collection["kind"] == "collection"
    assert md_collection["members_count"] == 2
    assert chunk_collection["kind"] == "collection"
    assert chunk_collection["members_count"] == 2
