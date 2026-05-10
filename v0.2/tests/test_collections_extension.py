from pathlib import Path
from typing import Any, cast

from dorje.extensions import load_extensions
from dorje.handles import HandleStore


def test_inspect_and_filter_collection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = HandleStore()
    (tmp_path / "a.html").write_text("<h1>A</h1>", encoding="utf-8")
    (tmp_path / "b.pdf").write_bytes(b"%PDF")
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    source = cast(dict[str, Any], registry.call("ls_as_handles", {"path": str(tmp_path), "glob": "*"}))
    summary = cast(dict[str, Any], registry.call("inspect_collection", {"handle": source["handle"]}))

    assert summary["members_count"] == 2
    assert summary["by_media_type"] == {"application/pdf": 1, "text/html": 1}

    filtered = cast(
        dict[str, Any],
        registry.call("filter_collection", {"handle": source["handle"], "media_type": "text/html"}),
    )

    assert filtered["members_count"] == 1
    assert filtered["skipped_count"] == 1
    collection = store.get(cast(str, filtered["handle"]))
    assert collection.kind == "collection"
    assert collection.derivative_type == "collection"
    assert collection.members[0]["media_type"] == "text/html"
