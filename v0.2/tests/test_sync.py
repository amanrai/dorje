import hashlib
from pathlib import Path

import orjson

from dorje.sync import sync_corpus


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_sync_corpus_builds_hash_keyed_manifest_and_diffs_content(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    alpha = _sha("alpha")

    first = sync_corpus(tmp_path)

    assert first.added == [alpha]
    assert first.modified == []
    assert first.deleted == []
    assert first.total_sources == 1
    manifest_path = tmp_path / ".dorje" / "source_manifest.json"
    manifest = orjson.loads(manifest_path.read_bytes())
    assert list(manifest["sources"]) == [alpha]
    assert manifest["sources"][alpha]["paths"] == ["a.txt"]
    assert manifest["sources"][alpha]["sha256"] == alpha

    second = sync_corpus(tmp_path)

    assert second.added == []
    assert second.modified == []
    assert second.deleted == []
    assert second.unchanged == [alpha]

    (tmp_path / "a.txt").write_text("alpha changed", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    alpha_changed = _sha("alpha changed")
    beta = _sha("beta")

    third = sync_corpus(tmp_path)

    assert third.added == sorted([alpha_changed, beta])
    assert third.modified == []
    assert third.deleted == [alpha]

    (tmp_path / "a.txt").unlink()

    fourth = sync_corpus(tmp_path)

    assert fourth.deleted == [alpha_changed]
    assert fourth.unchanged == [beta]


def test_sync_groups_duplicate_paths_by_hash(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("same", encoding="utf-8")
    (tmp_path / "b.txt").write_text("same", encoding="utf-8")
    digest = _sha("same")

    result = sync_corpus(tmp_path)

    assert result.added == [digest]
    assert result.total_sources == 1
    manifest = orjson.loads((tmp_path / ".dorje" / "source_manifest.json").read_bytes())
    assert manifest["sources"][digest]["paths"] == ["a.txt", "b.txt"]


def test_sync_reports_path_occurrence_changes_as_modified(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("same", encoding="utf-8")
    digest = _sha("same")
    sync_corpus(tmp_path)
    (tmp_path / "b.txt").write_text("same", encoding="utf-8")

    result = sync_corpus(tmp_path)

    assert result.added == []
    assert result.deleted == []
    assert result.modified == [digest]


def test_sync_ignores_dorje_directory(tmp_path: Path) -> None:
    (tmp_path / ".dorje").mkdir()
    (tmp_path / ".dorje" / "internal.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "visible.txt").write_text("keep", encoding="utf-8")

    result = sync_corpus(tmp_path)

    assert result.added == [_sha("keep")]
