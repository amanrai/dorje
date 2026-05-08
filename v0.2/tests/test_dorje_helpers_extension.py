from pathlib import Path

from dorje.extensions import load_extensions


def test_get_dorje_helpers_docs_tool() -> None:
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    result = registry.call("get_dorje_helpers_docs", {})

    assert isinstance(result, str)
    assert "from dorje_helpers import" in result
