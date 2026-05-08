"""LM provider protocol."""

from typing import Protocol

from dorje_lm.types import LMHealth, LMRequest, LMResponse


class LMProvider(Protocol):
    """Minimal reusable language-model provider interface."""

    def complete(self, request: LMRequest) -> LMResponse:
        """Run one completion."""
        ...

    def health(self) -> LMHealth:
        """Return provider health."""
        ...

    def close(self) -> None:
        """Release provider resources."""
        ...
