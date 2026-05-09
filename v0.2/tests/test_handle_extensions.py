from pathlib import Path

from dorje.extensions import load_extensions


def test_handle_tools_and_chunk_handle() -> None:
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    stored = registry.call(
        "store_handle",
        {"content": "A paragraph.\n\nAnother paragraph.", "content_type": "text/markdown"},
    )
    assert isinstance(stored, dict)
    handle = stored["handle"]
    assert isinstance(handle, str)

    read = registry.call("read_handle_into_context", {"handle": handle})
    assert isinstance(read, dict)
    assert read["content"] == "A paragraph.\n\nAnother paragraph."

    chunks = registry.call("chunk_md_handle", {"handle": handle, "max_chars": 20})
    assert isinstance(chunks, list)
    assert len(chunks) == 2
    assert isinstance(chunks[0], dict)
    assert "handle" in chunks[0]
