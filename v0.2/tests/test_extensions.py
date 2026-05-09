from pathlib import Path

from dorje.extensions import default_extension_roots, load_extensions


def test_default_roots_include_bundled_then_corpus_then_home(tmp_path: Path) -> None:
    roots = default_extension_roots(cwd=tmp_path, home=tmp_path / "home")

    assert roots[0].name == "base_extensions"
    assert roots[1] == tmp_path / ".dorje" / "extensions"
    assert roots[2] == tmp_path / "home" / ".dorje" / "extensions"


def test_builtin_tools() -> None:
    registry = load_extensions(roots=())

    assert registry.call("add", {"a": 2, "b": 3}) == 5
    assert registry.call("echo", {"value": {"ok": True}}) == {"ok": True}


def test_folder_extension_tool(tmp_path: Path) -> None:
    ext_dir = tmp_path / "sample"
    ext_dir.mkdir()
    (ext_dir / "extension.py").write_text(
        "from dorje_sdk import tool\n\n"
        "@tool(description='Join two strings.')\n"
        "def join(left, right):\n"
        "    return left + right\n",
        encoding="utf-8",
    )

    registry = load_extensions(roots=(tmp_path,))

    assert registry.call("join", {"left": "a", "right": "b"}) == "ab"
