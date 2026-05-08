"""Deterministic test LM provider."""

from dorje_lm.types import LMHealth, LMRequest, LMResponse


class EchoProvider:
    """Provider used for tests and plumbing checks."""

    def complete(self, request: LMRequest) -> LMResponse:
        return LMResponse(text=request.prompt, model=request.model, provider="echo")

    def health(self) -> LMHealth:
        return LMHealth(ok=True, provider="echo", message="ok")

    def close(self) -> None:
        return
