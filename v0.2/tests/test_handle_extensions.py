from pathlib import Path

from dorje.extensions import load_extensions


def test_handle_tools_and_markdown_paragraph_chunker() -> None:
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

    chunks = registry.call("chunk_markdown_paragraphs", {"handle": handle, "max_chars": 20})
    assert isinstance(chunks, dict)
    assert chunks["members_count"] == 2
