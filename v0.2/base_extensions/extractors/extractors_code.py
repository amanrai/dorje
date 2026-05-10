"""Code extractors."""

from __future__ import annotations

import ast
import re
from typing import Any

from dorje.handles import HandleStore
from dorje_sdk import tool
from extractors_common import CSS_MEDIA_TYPES, JAVASCRIPT_MEDIA_TYPES, PYTHON_MEDIA_TYPES, collection_result, get_file_ref, member


@tool(description="Extract Python classes/functions as code symbol derivative handles from a Python file_ref handle.", produces="code_symbol_collection/code_symbol")
def extract_python_symbols(handle: str, label: str = "") -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type not in PYTHON_MEDIA_TYPES and not record.label.endswith(".py"):
        raise ValueError("extract_python_symbols requires a Python file_ref handle")
    lines = record.content.splitlines()
    members: list[dict[str, Any]] = []
    for node in ast.walk(ast.parse(record.content)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        output = _put_code_symbol(store, record, lines, node.lineno, getattr(node, "end_lineno", node.lineno), node.name, kind, "extract_python_symbols", "text/x-code-python", label)
        members.append(member(output))
    collection = store.put_collection(members, label=label or f"{record.label or record.handle} python symbols", metadata={"derived_from": record.handle, "extractor": "extract_python_symbols"}, derivative_type="code_symbol_collection")
    return collection_result(record.handle, collection, members)


@tool(description="Extract JavaScript/TypeScript classes/functions/components as code symbol derivative handles.", produces="code_symbol_collection/code_symbol")
def extract_js_symbols(handle: str, label: str = "") -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type not in JAVASCRIPT_MEDIA_TYPES and not record.label.endswith((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")):
        raise ValueError("extract_js_symbols requires a JavaScript/TypeScript file_ref handle")
    lines = record.content.splitlines()
    members: list[dict[str, Any]] = []
    for name, kind, start in _js_symbol_matches(lines):
        end = _brace_block_end(lines, start)
        output = _put_code_symbol(store, record, lines, start, end, name, kind, "extract_js_symbols", record.content_type, label)
        members.append(member(output))
    collection = store.put_collection(members, label=label or f"{record.label or record.handle} js symbols", metadata={"derived_from": record.handle, "extractor": "extract_js_symbols"}, derivative_type="code_symbol_collection")
    return collection_result(record.handle, collection, members)


@tool(description="Extract CSS/SCSS/Sass/Less rule blocks as stylesheet rule derivatives.", produces="style_rule_collection/style_rule")
def extract_css_rules(handle: str, label: str = "") -> dict[str, object]:
    store = HandleStore()
    record = get_file_ref(store, handle)
    if record.content_type not in CSS_MEDIA_TYPES and not record.label.endswith((".css", ".scss", ".sass", ".less")):
        raise ValueError("extract_css_rules requires a CSS/SCSS/Sass/Less file_ref handle")
    lines = record.content.splitlines()
    members: list[dict[str, Any]] = []
    for index, (selector, start, end) in enumerate(_css_rule_matches(lines), start=1):
        output = store.put(
            "\n".join(lines[start - 1 : end]) + "\n",
            content_type=record.content_type,
            label=f"{label or record.label or record.handle}::{selector[:80] or f'rule_{index}'}",
            index_state="indexable",
            metadata={"derived_from": record.handle, "extractor": "extract_css_rules", "source_media_type": record.content_type, "rule_index": index, "selector": selector, "start_line": start, "end_line": end},
            derivative_type="style_rule",
        )
        members.append(member(output))
    collection = store.put_collection(members, label=label or f"{record.label or record.handle} css rules", metadata={"derived_from": record.handle, "extractor": "extract_css_rules"}, derivative_type="style_rule_collection")
    return collection_result(record.handle, collection, members)


def _put_code_symbol(store: HandleStore, record, lines: list[str], start: int, end: int, name: str, kind: str, extractor: str, content_type: str, label: str):
    return store.put(
        "\n".join(lines[start - 1 : end]) + "\n",
        content_type=content_type,
        label=f"{label or record.label or record.handle}::{name}",
        index_state="indexable",
        metadata={"derived_from": record.handle, "extractor": extractor, "source_media_type": record.content_type, "symbol_name": name, "symbol_kind": kind, "start_line": start, "end_line": end},
        derivative_type="code_symbol",
    )


def _js_symbol_matches(lines: list[str]) -> list[tuple[str, str, int]]:
    patterns: tuple[tuple[str, str], ...] = (
        (r"^\s*export\s+default\s+function\s+([A-Za-z_$][\w$]*)", "function"),
        (r"^\s*export\s+function\s+([A-Za-z_$][\w$]*)", "function"),
        (r"^\s*function\s+([A-Za-z_$][\w$]*)", "function"),
        (r"^\s*export\s+class\s+([A-Za-z_$][\w$]*)", "class"),
        (r"^\s*class\s+([A-Za-z_$][\w$]*)", "class"),
        (r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", "function"),
        (r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function", "function"),
    )
    matches: list[tuple[str, str, int]] = []
    for lineno, line in enumerate(lines, start=1):
        for pattern, kind in patterns:
            found = re.search(pattern, line)
            if found:
                matches.append((found.group(1), kind, lineno))
                break
    return matches


def _brace_block_end(lines: list[str], start_line: int) -> int:
    depth = 0
    seen_open = False
    for lineno in range(start_line, len(lines) + 1):
        line = lines[lineno - 1]
        depth += line.count("{")
        seen_open = seen_open or "{" in line
        depth -= line.count("}")
        if seen_open and depth <= 0:
            return lineno
    return start_line


def _css_rule_matches(lines: list[str]) -> list[tuple[str, int, int]]:
    matches: list[tuple[str, int, int]] = []
    start = 0
    selector_parts: list[str] = []
    depth = 0
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("/*"):
            continue
        if depth == 0 and "{" in stripped:
            start = lineno
            selector_parts = [stripped.split("{", 1)[0].strip()]
        elif depth == 0 and start == 0:
            selector_parts = [*selector_parts, stripped]
        depth += line.count("{")
        depth -= line.count("}")
        if start and depth <= 0:
            matches.append((" ".join(part for part in selector_parts if part).strip(), start, lineno))
            start = 0
            selector_parts = []
            depth = 0
    return matches
