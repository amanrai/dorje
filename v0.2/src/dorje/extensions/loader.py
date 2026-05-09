"""Folder-based extension discovery and loading."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
import dorje.extensions.builtin as builtin_tools
from dorje.extensions.registry import ToolRegistry, ToolSpec

EXTENSION_FILE = "extension.py"


def default_extension_roots(cwd: Path | None = None, home: Path | None = None) -> tuple[Path, ...]:
    """Return extension roots in precedence order.

    Bundled/default extensions come from the installed Dorje distribution, not
    the folder where ``dorje`` is invoked. Corpus-local extensions live under
    ``./.dorje/extensions``.
    """
    resolved_cwd = cwd if cwd is not None else Path.cwd()
    resolved_home = home if home is not None else Path.home()
    return (
        bundled_extension_root(),
        resolved_cwd / ".dorje" / "extensions",
        resolved_home / ".dorje" / "extensions",
    )


def bundled_extension_root() -> Path:
    """Return the bundled extension root for this Dorje install."""
    return Path(__file__).resolve().parents[3] / "base_extensions"


def load_extensions(roots: Iterable[Path] | None = None) -> ToolRegistry:
    """Discover extension folders and return a populated registry."""
    registry = ToolRegistry()
    _register_module_tools(registry, "builtin", builtin_tools)
    extension_roots = tuple(roots) if roots is not None else default_extension_roots()
    seen_extensions: set[str] = set()

    for root in extension_roots:
        if not root.exists():
            continue
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            if folder.name in seen_extensions:
                continue
            extension_file = folder / EXTENSION_FILE
            if not extension_file.exists():
                continue
            seen_extensions.add(folder.name)
            module = _load_module(folder.name, extension_file)
            _register_module_tools(registry, folder.name, module)

    return registry


def _load_module(extension_name: str, path: Path) -> ModuleType:
    module_name = f"_dorje_extension_{extension_name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load extension: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _register_module_tools(registry: ToolRegistry, extension_name: str, module: ModuleType) -> None:
    for value in vars(module).values():
        if not callable(value):
            continue
        if getattr(value, "__dorje_tool__", False) is not True:
            continue
        name = getattr(value, "__dorje_tool_name__", None)
        description = getattr(value, "__dorje_tool_description__", "")
        if not isinstance(name, str) or len(name) == 0:
            raise ValueError(f"invalid tool name in extension: {extension_name}")
        registry.register(
            ToolSpec(
                name=name,
                description=description if isinstance(description, str) else "",
                extension_name=extension_name,
                callable=value,
            )
        )
