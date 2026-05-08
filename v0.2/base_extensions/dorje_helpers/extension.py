"""Dorje helper documentation extension."""

from __future__ import annotations

from dorje_helpers import docs
from dorje_sdk import tool


@tool(description="Get documentation for helper functions available inside run_python code.")
def get_dorje_helpers_docs() -> str:
    """Return Dorje helper docs for code-writing tasks."""
    return docs()
