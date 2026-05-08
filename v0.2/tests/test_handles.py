from pathlib import Path

from dorje.handles import HandleStore


def test_handle_store_round_trip(tmp_path: Path) -> None:
    store = HandleStore(root=tmp_path)

    record = store.put("hello", content_type="text/plain", label="greeting")
    loaded = store.get(record.handle)

    assert loaded.content == "hello"
    assert loaded.content_type == "text/plain"
    assert loaded.label == "greeting"
