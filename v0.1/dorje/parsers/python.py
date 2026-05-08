"""Python parser — tree-sitter based AST extraction."""

from __future__ import annotations

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Node

from dorje.parsers import register
from dorje.types import ASTContext, Chunk, ChunkMetadata, GraphNode, SemanticUnit, Triple

_PY_LANGUAGE = Language(tspython.language())
_STRUCTURAL_TYPES = frozenset({
    "function_definition",
    "class_definition",
    "decorated_definition",
})
_MAX_AST_DEPTH = 50


def _create_parser() -> Parser:
    """Create a tree-sitter parser for Python."""
    parser = Parser(_PY_LANGUAGE)
    return parser


def _get_name(node: Node) -> str:
    """Extract the name from a function/class definition node."""
    assert node is not None, "node must not be None"
    for child in node.children:
        if child.type == "identifier":
            return child.text.decode("utf-8") if child.text else ""
    return ""


def _get_docstring(node: Node) -> str | None:
    """Extract docstring from a function/class body."""
    body = None
    for child in node.children:
        if child.type == "block":
            body = child
            break

    if body is None or len(body.children) == 0:
        return None

    first_stmt = body.children[0]
    if first_stmt.type == "expression_statement" and len(first_stmt.children) > 0:
        expr = first_stmt.children[0]
        if expr.type == "string":
            raw = expr.text.decode("utf-8") if expr.text else ""
            return raw.strip("\"'").strip()
    return None


def _get_parameters(node: Node) -> tuple[str, ...]:
    """Extract parameter list from a function definition."""
    for child in node.children:
        if child.type == "parameters":
            params: list[str] = []
            max_params = 100
            count = 0
            for param in child.children:
                if param.type in ("identifier", "typed_parameter",
                                  "default_parameter", "typed_default_parameter",
                                  "list_splat_pattern", "dictionary_splat_pattern"):
                    count += 1
                    assert count <= max_params, f"Too many parameters (>{max_params})"
                    params.append(param.text.decode("utf-8") if param.text else "")
            return tuple(params)
    return ()


def _get_return_type(node: Node) -> str | None:
    """Extract return type annotation from a function definition."""
    for child in node.children:
        if child.type == "type":
            return child.text.decode("utf-8") if child.text else None
    return None


def _get_decorators(node: Node) -> tuple[str, ...]:
    """Extract decorators from a decorated definition."""
    decorators: list[str] = []
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type == "decorator":
                text = child.text.decode("utf-8") if child.text else ""
                decorators.append(text.lstrip("@").strip())
    return tuple(decorators)


def _get_visibility(name: str) -> str:
    """Determine visibility from naming convention."""
    if name.startswith("__") and not name.endswith("__"):
        return "private"
    if name.startswith("_"):
        return "protected"
    return "public"


def _count_branches(node: Node, depth: int = 0) -> int:
    """Count cyclomatic cyclomatic_branch_count (branch points)."""
    assert depth < _MAX_AST_DEPTH, f"AST depth exceeds {_MAX_AST_DEPTH}"

    branch_types = frozenset({"if_statement", "elif_clause", "for_statement",
                               "while_statement", "except_clause", "with_statement",
                               "conditional_expression", "boolean_operator"})
    count = 1 if node.type in branch_types else 0
    for child in node.children:
        count += _count_branches(child, depth + 1)
    return count


def _collect_calls(node: Node, depth: int = 0) -> tuple[str, ...]:
    """Collect all function calls within a node."""
    assert depth < _MAX_AST_DEPTH, f"AST depth exceeds {_MAX_AST_DEPTH}"

    calls: list[str] = []
    max_calls = 500

    if node.type == "call":
        func_node = node.children[0] if node.children else None
        if func_node and func_node.text:
            calls.append(func_node.text.decode("utf-8"))

    for child in node.children:
        # Don't recurse into nested function/class definitions
        if child.type in _STRUCTURAL_TYPES:
            continue
        calls.extend(_collect_calls(child, depth + 1))

    assert len(calls) <= max_calls, f"Too many calls collected (>{max_calls})"
    return tuple(dict.fromkeys(calls))  # Deduplicate, preserve order


def _collect_imports(node: Node) -> tuple[str, ...]:
    """Collect import names from module-level import statements."""
    imports: list[str] = []
    max_imports = 500

    for child in node.children:
        if child.type == "import_statement":
            for name_node in child.children:
                if name_node.type == "dotted_name" and name_node.text:
                    imports.append(name_node.text.decode("utf-8"))
        elif child.type == "import_from_statement":
            # Get the module being imported from
            for name_node in child.children:
                if name_node.type == "dotted_name" and name_node.text:
                    imports.append(name_node.text.decode("utf-8"))
                    break

    assert len(imports) <= max_imports, f"Too many imports (>{max_imports})"
    return tuple(dict.fromkeys(imports))


def _collect_import_map(
    node: Node,
    file_path: str | None = None,
) -> dict[str, str]:
    """Build local_name -> qualified_origin map from import statements.

    file_path is needed to resolve relative imports (e.g. from .services.git
    in scryer/main.py -> scryer.services.git). Without it, relative imports
    use the dotted suffix only (services.git).

    Examples:
      from dorje.messaging import close_messaging  =>  close_messaging -> dorje.messaging.close_messaging
      from dorje.events import close_event_log as elog  =>  elog -> dorje.events.close_event_log
      import asyncio  =>  asyncio -> asyncio
      import os.path  =>  os -> os.path (top-level name only)
      from .services.git import ensure_repo  =>  ensure_repo -> <package>.services.git.ensure_repo
    """
    result: dict[str, str] = {}
    max_imports = 500

    # Derive package prefix from file path for relative import resolution
    package_parts: list[str] = []
    if file_path:
        module_dotted = file_path.replace("/", ".").removesuffix(".py")
        package_parts = module_dotted.split(".")[:-1]  # drop the filename

    for child in node.children:
        if child.type == "import_statement":
            # import X, import X.Y.Z
            for name_node in child.children:
                if name_node.type == "dotted_name" and name_node.text:
                    full = name_node.text.decode("utf-8")
                    local = full.split(".")[0]
                    result[local] = full
                elif name_node.type == "aliased_import":
                    _parse_aliased_import(name_node, None, result)

        elif child.type == "import_from_statement":
            module_name = None
            saw_import = False

            for sub in child.children:
                if sub.type == "dotted_name" and not saw_import:
                    module_name = sub.text.decode("utf-8") if sub.text else None
                elif sub.type == "relative_import":
                    module_name = _resolve_relative_import(sub, package_parts)
                elif sub.text and sub.text == b"import":
                    saw_import = True
                elif saw_import and sub.type == "dotted_name" and sub.text:
                    name = sub.text.decode("utf-8")
                    if module_name:
                        result[name] = f"{module_name}.{name}"
                elif saw_import and sub.type == "aliased_import":
                    _parse_aliased_import(sub, module_name, result)

        assert len(result) <= max_imports, f"Too many imports (>{max_imports})"

    return result


def _resolve_relative_import(
    node: Node,
    package_parts: list[str],
) -> str | None:
    """Resolve a relative_import node to an absolute module name.

    from .services.git  with package [scryer] -> scryer.services.git
    from ..utils        with package [scryer, sub] -> scryer.utils
    from .              with package [scryer] -> scryer
    """
    dot_count = 0
    relative_module = None

    for child in node.children:
        if child.type == "import_prefix" and child.text:
            dot_count = len(child.text.decode("utf-8"))
        elif child.type == "dotted_name" and child.text:
            relative_module = child.text.decode("utf-8")

    # Go up dot_count - 1 levels from the package
    # (one dot = current package, two dots = parent package, etc.)
    levels_up = max(dot_count - 1, 0)
    if levels_up > len(package_parts):
        # Can't resolve — goes above the known root
        return relative_module

    base_parts = package_parts[:len(package_parts) - levels_up]

    if relative_module:
        if base_parts:
            return f"{'.'.join(base_parts)}.{relative_module}"
        return relative_module

    if base_parts:
        return ".".join(base_parts)

    return None


def _parse_aliased_import(
    node: Node,
    module_name: str | None,
    result: dict[str, str],
) -> None:
    """Parse 'X as Y' in import statements."""
    original = None
    alias = None
    for child in node.children:
        if child.type == "dotted_name" and child.text:
            original = child.text.decode("utf-8")
        elif child.type == "identifier" and child.text:
            alias = child.text.decode("utf-8")

    if original and alias:
        qualified = f"{module_name}.{original}" if module_name else original
        result[alias] = qualified
    elif original:
        qualified = f"{module_name}.{original}" if module_name else original
        local = original.split(".")[0]
        result[local] = qualified


def _find_inner_def(node: Node) -> Node:
    """For decorated_definition, find the inner function/class definition."""
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                return child
    return node


def _qualified_name(name: str, parent_name: str | None, module_path: str) -> str:
    """Build a qualified name like 'module.Class.method'."""
    module = module_path.replace("/", ".").removesuffix(".py")
    if parent_name:
        return f"{module}.{parent_name}.{name}"
    return f"{module}.{name}"


def _extract_structural_units(
    node: Node,
    path: str,
    parent_name: str | None,
    parent_kind: str | None,
    module_imports: tuple[str, ...],
    depth: int,
) -> list[ASTContext]:
    """Recursively extract structural units from the AST."""
    assert depth < _MAX_AST_DEPTH, f"AST depth exceeds {_MAX_AST_DEPTH}"

    results: list[ASTContext] = []
    max_units = 5000

    for child in node.children:
        if child.type not in _STRUCTURAL_TYPES:
            continue

        decorators = _get_decorators(child)
        inner = _find_inner_def(child)
        name = _get_name(inner)

        if not name:
            continue

        kind = "class" if inner.type == "class_definition" else "function"
        if parent_kind == "class":
            kind = "method"

        params = _get_parameters(inner) if kind != "class" else ()
        return_type = _get_return_type(inner) if kind != "class" else None
        docstring = _get_docstring(inner)
        visibility = _get_visibility(name)
        cyclomatic_branch_count = _count_branches(inner)
        calls = _collect_calls(inner)

        qname = _qualified_name(name, parent_name, path)

        ctx = ASTContext(
            name=name,
            qualified_name=qname,
            kind=kind,
            parent_name=parent_name,
            parent_kind=parent_kind,
            module_path=path,
            parameters=params,
            return_type=return_type,
            decorators=decorators,
            docstring=docstring,
            visibility=visibility,
            cyclomatic_branch_count=cyclomatic_branch_count,
            imports_used=module_imports,
            calls_made=calls,
        )
        results.append(ctx)

        assert len(results) <= max_units, f"Too many structural units (>{max_units})"

        # Recurse into class bodies for methods
        if inner.type == "class_definition":
            nested = _extract_structural_units(
                inner, path, name, "class", module_imports, depth + 1
            )
            results.extend(nested)

    return results


@register
class PythonParser:
    """Python language parser using tree-sitter."""

    name = "python"
    extensions = [".py"]

    def parse(self, source: str, path: str) -> list[SemanticUnit]:
        """Parse Python source into semantic units.

        Always emits a module unit (full file) first, then child units
        for each function, class, and method.
        """
        assert source, "source must not be empty"
        assert path, "path must not be empty"

        contexts = self.extract_ast_context(source, path)
        source_bytes = source.encode("utf-8")
        lines = source.splitlines(keepends=True)
        total_lines = len(lines)
        module_name = path.replace("/", ".").removesuffix(".py")

        # Collect module-level imports
        imports: tuple[str, ...] = ()
        if contexts and contexts[0].imports_used:
            imports = contexts[0].imports_used

        # Module unit — always first
        module_metadata = ChunkMetadata(
            name=module_name,
            qualified_name=module_name,
            kind="module",
            parent_name=None,
            parent_kind=None,
            parameters=None,
            return_type=None,
            decorators=None,
            docstring=None,
            visibility="public",
            cyclomatic_branch_count=None,
            imports_used=imports,
            calls_made=None,
        )

        module_unit = SemanticUnit(
            kind="module",
            name=module_name,
            qualified_name=module_name,
            path=path,
            start_line=0,
            end_line=max(total_lines - 1, 0),
            content=source,
            language="python",
            metadata=module_metadata,
            parent_unit_id=None,
            pass_name="semantic_unit",
        )

        units: list[SemanticUnit] = [module_unit]

        # Child units from AST contexts
        for ctx in contexts:
            content = _extract_source_for_context(ctx, source_bytes, lines, path)
            if content is None:
                continue

            start_line, end_line, text = content

            parent_id = module_name
            if ctx.parent_name and ctx.parent_kind == "class":
                parent_id = f"{module_name}.{ctx.parent_name}"

            units.append(SemanticUnit(
                kind=ctx.kind,
                name=ctx.name,
                qualified_name=ctx.qualified_name,
                path=path,
                start_line=start_line,
                end_line=end_line,
                content=text,
                language="python",
                metadata=ctx.to_chunk_metadata(),
                parent_unit_id=parent_id,
                pass_name="semantic_unit",
            ))

        return units

    def extract_ast_context(self, source: str, path: str) -> list[ASTContext]:
        """Extract AST context for all structural units."""
        assert source, "source must not be empty"
        assert path, "path must not be empty"

        parser = _create_parser()
        tree = parser.parse(source.encode("utf-8"))
        assert tree.root_node is not None, "Failed to parse source"

        module_imports = _collect_imports(tree.root_node)

        return _extract_structural_units(
            tree.root_node, path, None, None, module_imports, depth=0
        )

    def build_graph(self, source: str, path: str) -> tuple[list[GraphNode], list[Triple]]:
        """Build graph nodes and triples from Python source."""
        assert source, "source must not be empty"
        assert path, "path must not be empty"

        contexts = self.extract_ast_context(source, path)
        parser = _create_parser()
        tree = parser.parse(source.encode("utf-8"))
        module_imports = _collect_imports(tree.root_node)

        module_name = path.replace("/", ".").removesuffix(".py")
        nodes: list[GraphNode] = []
        triples: list[Triple] = []

        # Module node
        module_node = GraphNode(
            id=module_name,
            kind="module",
            label=module_name,
            path=path,
            line=0,
            metadata={},
        )
        nodes.append(module_node)

        # Import triples
        for imp in module_imports:
            triples.append(Triple(
                subject=module_name,
                verb="imports",
                object=imp,
                source="ast",
                bidirectional=False,
                metadata={},
            ))

        # Structural unit nodes and triples
        for ctx in contexts:
            node = GraphNode(
                id=ctx.qualified_name,
                kind=ctx.kind,
                label=ctx.name,
                path=path,
                line=None,  # Would need line tracking — added during parse
                metadata={"visibility": ctx.visibility},
            )
            nodes.append(node)

            # Containment
            parent_id = (
                f"{module_name}.{ctx.parent_name}" if ctx.parent_name else module_name
            )
            triples.append(Triple(
                subject=parent_id,
                verb="contains",
                object=ctx.qualified_name,
                source="ast",
                bidirectional=False,
                metadata={},
            ))

            # Calls
            for call in ctx.calls_made:
                triples.append(Triple(
                    subject=ctx.qualified_name,
                    verb="calls",
                    object=call,
                    source="ast",
                    bidirectional=False,
                    metadata={},
                ))

            # Inheritance (for classes)
            if ctx.kind == "class":
                bases = _get_class_bases(tree.root_node, ctx.name)
                for base in bases:
                    triples.append(Triple(
                        subject=ctx.qualified_name,
                        verb="inherits",
                        object=base,
                        source="ast",
                        bidirectional=False,
                        metadata={},
                    ))

        return nodes, triples


def _extract_source_for_context(
    ctx: ASTContext,
    source_bytes: bytes,
    lines: list[str],
    path: str,
) -> tuple[int, int, str] | None:
    """Find the source text for an AST context by re-parsing and matching."""
    parser = _create_parser()
    tree = parser.parse(source_bytes)

    match = _find_node_by_name(tree.root_node, ctx.name, ctx.kind, depth=0)
    if match is None:
        return None

    start_line = match.start_point[0]
    end_line = match.end_point[0]
    text = "".join(lines[start_line:end_line + 1])

    if not text.strip():
        return None

    return start_line, end_line, text


def _find_node_by_name(
    node: Node,
    name: str,
    kind: str,
    depth: int,
) -> Node | None:
    """Find a structural node by name and kind."""
    assert depth < _MAX_AST_DEPTH, f"AST depth exceeds {_MAX_AST_DEPTH}"

    kind_to_type = {
        "function": "function_definition",
        "method": "function_definition",
        "class": "class_definition",
    }
    target_type = kind_to_type.get(kind)

    for child in node.children:
        inner = _find_inner_def(child) if child.type == "decorated_definition" else child

        if inner.type == target_type and _get_name(inner) == name:
            # Return the decorated_definition if it exists, for full source
            return child if child.type == "decorated_definition" else inner

        # Recurse into class bodies
        if inner.type == "class_definition":
            result = _find_node_by_name(inner, name, kind, depth + 1)
            if result is not None:
                return result

    return None


def _get_class_bases(root: Node, class_name: str) -> tuple[str, ...]:
    """Extract base classes for a named class."""
    for child in root.children:
        inner = _find_inner_def(child) if child.type == "decorated_definition" else child
        if inner.type == "class_definition" and _get_name(inner) == class_name:
            for arg_list in inner.children:
                if arg_list.type == "argument_list":
                    bases: list[str] = []
                    for arg in arg_list.children:
                        if arg.type in ("identifier", "attribute") and arg.text:
                            bases.append(arg.text.decode("utf-8"))
                    return tuple(bases)
    return ()
