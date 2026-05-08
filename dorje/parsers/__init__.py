"""Parser registry — plugin architecture for language-specific AST parsing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dorje.types import ASTContext, GraphNode, SemanticUnit, Triple

_REGISTRY: dict[str, type[LanguageParser]] = {}


@runtime_checkable
class LanguageParser(Protocol):
    """Interface every language parser must implement."""

    name: str
    extensions: list[str]

    def parse(self, source: str, path: str) -> list[SemanticUnit]:
        """Parse source code into semantic units (module + children)."""
        ...

    def extract_ast_context(self, source: str, path: str) -> list[ASTContext]:
        """Extract AST context for each structural unit."""
        ...

    def build_graph(self, source: str, path: str) -> tuple[list[GraphNode], list[Triple]]:
        """Extract graph nodes and triples."""
        ...


def register(parser_cls: type[LanguageParser]) -> type[LanguageParser]:
    """Decorator to register a parser for its file extensions."""
    assert hasattr(parser_cls, "extensions"), (
        f"Parser {parser_cls.__name__} must have 'extensions' attribute"
    )
    assert hasattr(parser_cls, "name"), (
        f"Parser {parser_cls.__name__} must have 'name' attribute"
    )

    extensions = parser_cls.extensions
    assert isinstance(extensions, list), "extensions must be a list"
    assert len(extensions) > 0, f"Parser {parser_cls.__name__} must register at least one extension"

    for ext in extensions:
        assert ext.startswith("."), f"Extension must start with '.', got '{ext}'"
        _REGISTRY[ext] = parser_cls

    return parser_cls


def get_parser(extension: str) -> LanguageParser:
    """Get parser for a file extension. Falls back to line-based parser."""
    assert isinstance(extension, str), f"extension must be a string, got {type(extension).__name__}"

    from dorje.parsers.fallback import FallbackParser

    cls = _REGISTRY.get(extension.lower(), FallbackParser)
    return cls()


def registered_extensions() -> list[str]:
    """Return all registered file extensions."""
    return sorted(_REGISTRY.keys())


def _load_all_parsers() -> None:
    """Import all parser modules to trigger registration."""
    import dorje.parsers.fallback  # noqa: F401
    import dorje.parsers.python  # noqa: F401


# Auto-load on import
_load_all_parsers()
