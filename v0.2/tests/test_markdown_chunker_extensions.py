from pathlib import Path
from typing import Any, cast

import pytest

from dorje.extensions import load_extensions
from dorje.handles import HandleStore


def _registry():
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    return load_extensions(roots=(root,))


def test_chunk_full_text_passthrough(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = HandleStore().put("# Title\n\nBody", content_type="text/markdown", derivative_type="extracted_markdown")

    result = cast(dict[str, Any], _registry().call("chunk_full_text", {"handle": source.handle}))

    assert result["derivative_type"] == "collection"
    collection = HandleStore().get(cast(str, result["handle"]))
    assert len(collection.members) == 1
    chunk = HandleStore().get(cast(str, collection.members[0]["handle"]))
    assert chunk.derivative_type == "full_text_chunk"
    assert chunk.metadata["chunk_type"] == "text/full"


def test_chunk_markdown_sections(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = HandleStore().put("# A\n\nAlpha\n\n## B\n\nBeta", content_type="text/markdown", derivative_type="extracted_markdown")

    result = cast(dict[str, Any], _registry().call("chunk_markdown_sections", {"handle": source.handle}))

    collection = HandleStore().get(cast(str, result["handle"]))
    assert len(collection.members) == 2
    first = HandleStore().get(cast(str, collection.members[0]["handle"]))
    second = HandleStore().get(cast(str, collection.members[1]["handle"]))
    assert first.metadata["chunk_type"] == "text/section"
    assert first.metadata["section_path"] == ["A"]
    assert second.metadata["section_path"] == ["A", "B"]


def test_chunk_markdown_paragraphs_and_sentences(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = HandleStore().put("One. Two.\n\nThree.", content_type="text/markdown", derivative_type="extracted_markdown")
    registry = _registry()

    paragraphs = cast(dict[str, Any], registry.call("chunk_markdown_paragraphs", {"handle": source.handle, "max_chars": 8}))
    sentences = cast(dict[str, Any], registry.call("chunk_markdown_sentences", {"handle": source.handle, "max_chars": 6}))

    paragraph_collection = HandleStore().get(cast(str, paragraphs["handle"]))
    sentence_collection = HandleStore().get(cast(str, sentences["handle"]))
    assert len(paragraph_collection.members) == 2
    assert len(sentence_collection.members) == 3
    assert HandleStore().get(cast(str, paragraph_collection.members[0]["handle"])).metadata["chunk_type"] == "text/paragraph"
    assert HandleStore().get(cast(str, sentence_collection.members[0]["handle"])).metadata["chunk_type"] == "text/sentence"


def test_chunk_markdown_strided_token_is_registered_placeholder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = HandleStore().put("hello", content_type="text/markdown", derivative_type="extracted_markdown")

    with pytest.raises(NotImplementedError, match="tokenizer integration"):
        _registry().call("chunk_markdown_strided_token", {"handle": source.handle})
