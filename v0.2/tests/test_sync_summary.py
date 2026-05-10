from pathlib import Path

from dorje.sync import sync_extract, sync_sources, sync_summary


def test_sync_summary_counts_handles_by_type(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    sync_sources(tmp_path)
    sync_extract(tmp_path)

    summary = sync_summary(tmp_path)

    assert summary["handles_total"] == 2
    assert summary["handles_by_kind"] == {"derivative": 1, "file_ref": 1}
    assert summary["handles_by_derivative_type"] == {"<none>": 1, "extracted_markdown": 1}
    assert summary["edges_by_type"] == {"derived_from": 1}
