from pathlib import Path

from dorje.extensions import load_extensions


def test_get_from_wikipedia_extension_is_discoverable() -> None:
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))
    tools = {spec.name for spec in registry.list()}

    assert "get_from_wikipedia" in tools
