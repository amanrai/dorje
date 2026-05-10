"""Extractor extension entrypoint.

Keep this file thin. Extractor families live in sibling modules so the extension
can grow to many file types without turning into one giant module.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

_MODULES = ("extractors_text", "extractors_html", "extractors_code", "extractors_pdf")


def _export_tools(module: ModuleType, namespace: dict[str, Any]) -> None:
    for name, value in vars(module).items():
        if getattr(value, "__dorje_tool__", False) is True:
            namespace[name] = value


for module_name in _MODULES:
    _export_tools(importlib.import_module(module_name), globals())
