"""Handle ontology definitions.

These are the top-level axes Dorje uses to reason about handles. They are
intentionally orthogonal: a handle's storage kind, provenance role, and
indexability are separate dimensions.

This module defines vocabulary first. Existing v0.2 handles can be interpreted
through these axes without requiring an immediate storage rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

HandleKind = Literal["derivative", "file_ref", "collection", "index"]
"""How a handle is represented/stored."""

ProvenanceRole = Literal["source", "artifact"]
"""Whether the handle points at original corpus material or Dorje-derived material."""

IndexState = Literal["raw", "indexable", "index", "metadata"]
"""How directly useful the handle is for indexing/search."""

MediaType = str
"""MIME/media type string, e.g. text/html, application/pdf, text/markdown."""

HandlePurpose = Literal["inspection", "conversion", "indexing", "search", "storage", "any"]
"""Declared purpose for a tool/helper handle contract."""


@dataclass(frozen=True, slots=True)
class HandleAxes:
    """Orthogonal metadata axes for a handle."""

    kind: HandleKind
    media_type: MediaType
    role: ProvenanceRole
    index_state: IndexState


@dataclass(frozen=True, slots=True)
class HandleContract:
    """Compatibility declaration for a tool/helper input or output.

    Empty tuples mean "any" for that axis. These contracts are descriptive for
    now; later they can be used for validation and agent-facing capability maps.
    """

    kinds: tuple[HandleKind, ...] = ()
    media_types: tuple[MediaType, ...] = ()
    roles: tuple[ProvenanceRole, ...] = ()
    index_states: tuple[IndexState, ...] = ()
    purpose: HandlePurpose = "any"
    description: str = ""

    def matches(self, axes: HandleAxes) -> bool:
        """Return true if these axes satisfy this contract."""
        return (
            (not self.kinds or axes.kind in self.kinds)
            and (not self.media_types or axes.media_type in self.media_types)
            and (not self.roles or axes.role in self.roles)
            and (not self.index_states or axes.index_state in self.index_states)
        )


@dataclass(frozen=True, slots=True)
class HandleDescriptor:
    """Agent-facing description of a handle without necessarily carrying content."""

    handle: str
    axes: HandleAxes
    label: str = ""
    path: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    char_count: int | None = None
    derived_from: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


DERIVATIVE_MARKDOWN_ARTIFACT = HandleAxes(
    kind="derivative",
    media_type="text/markdown",
    role="artifact",
    index_state="indexable",
)

DERIVATIVE_TEXT_ARTIFACT = HandleAxes(
    kind="derivative",
    media_type="text/plain",
    role="artifact",
    index_state="indexable",
)


def default_axes_for_derivative(media_type: str) -> HandleAxes:
    """Infer axes for a Dorje-produced derivative handle."""
    index_state: IndexState
    if media_type.startswith("text/") or media_type in ("application/json", "application/x-ndjson"):
        index_state = "indexable"
    else:
        index_state = "raw"
    return HandleAxes(
        kind="derivative",
        media_type=media_type,
        role="artifact",
        index_state=index_state,
    )


def file_ref_axes(media_type: str, role: ProvenanceRole = "source") -> HandleAxes:
    """Construct axes for an uncopied file reference handle."""
    index_state: IndexState = "indexable" if media_type.startswith("text/") else "raw"
    return HandleAxes(kind="file_ref", media_type=media_type, role=role, index_state=index_state)
