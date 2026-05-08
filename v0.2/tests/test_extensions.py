from pathlib import Path

from dorje.extensions import default_extension_roots, load_extensions


def test_default_roots_include_base_extensions(tmp_path: Path) -> None:
    roots = default_extension_roots(cwd=tmp_path, home=tmp_path / "home")

    assert roots[0] == tmp_path / "base_extensions"


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
