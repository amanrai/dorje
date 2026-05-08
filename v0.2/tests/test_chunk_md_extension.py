from pathlib import Path

from dorje.extensions import load_extensions


def test_chunk_md_extension_chunks_paragraphs() -> None:
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))
    result = registry.call(
        "chunk_md",
        {
            "markdown": "# Title\n\nFirst paragraph.\n\nSecond paragraph.\n\nThird paragraph.",
            "max_chars": 35,
        },
    )

    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], dict)
    assert "id" in result[0]
    assert result[0]["chunk"] == "# Title\n\nFirst paragraph."
