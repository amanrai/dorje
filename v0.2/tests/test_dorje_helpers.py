from pathlib import Path

from pytest import MonkeyPatch

from dorje.handles import HandleStore
from dorje_helpers import docs, iter_handles, read_handle, write_handle


def test_dorje_helpers_docs_mentions_run_python() -> None:
    assert "run_python" in docs()
    assert "read_handle" in docs()


def test_iter_handles_yields_handle_ids() -> None:
    assert list(iter_handles(["h_1", "h_2"])) == ["h_1", "h_2"]


def test_dorje_helpers_read_and_write_handle(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    written = write_handle("hello", content_type="text/plain", label="greeting")
    handle = written["handle"]
    assert isinstance(handle, str)

    read = read_handle(handle)

    assert read["content"] == "hello"
    assert read["content_type"] == "text/plain"
    assert HandleStore().get(handle).label == "greeting"
