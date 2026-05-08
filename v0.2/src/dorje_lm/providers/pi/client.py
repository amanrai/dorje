"""Pi-backed LM provider."""

from pathlib import Path
from typing import Any

from dorje_lm.errors import LMProviderError
from dorje_lm.providers.pi.sidecar import SidecarProcess
from dorje_lm.types import LMHealth, LMRequest, LMResponse


class PiProvider:
    """LM provider that delegates to a persistent Pi SDK sidecar."""

    def __init__(self, command: tuple[str, ...], model: str | None = None) -> None:
        self._model = model
        self._sidecar = SidecarProcess(command, cwd=Path.cwd())

    def complete(self, request: LMRequest) -> LMResponse:
        model = request.model if request.model is not None else self._model
        payload: dict[str, Any] = {
            "op": "complete",
            "prompt": request.prompt,
            "context": request.context,
            "output": request.output,
            "model": model,
            "system": request.system,
            "schema": request.schema,
        }
        response = self._sidecar.request(payload, request.timeout_s)
        self._raise_if_error(response)
        text = response.get("text")
        if not isinstance(text, str):
            raise LMProviderError("Pi sidecar response missing text")
        provider = response.get("provider")
        used_model = response.get("model")
        return LMResponse(
            text=text,
            provider=provider if isinstance(provider, str) else "pi",
            model=used_model if isinstance(used_model, str) else model,
            raw=response,
        )

    def health(self) -> LMHealth:
        response = self._sidecar.request({"op": "health"}, 10.0)
        self._raise_if_error(response)
        message = response.get("message")
        return LMHealth(
            ok=True,
            provider="pi",
            message=message if isinstance(message, str) else "ok",
            raw=response,
        )

    def close(self) -> None:
        self._sidecar.close()

    @staticmethod
    def _raise_if_error(response: dict[str, Any]) -> None:
        ok = response.get("ok")
        if ok is True:
            return
        error = response.get("error")
        if isinstance(error, str):
            raise LMProviderError(error)
        raise LMProviderError("Pi sidecar returned an error")
