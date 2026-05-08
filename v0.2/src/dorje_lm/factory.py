"""LM provider factory."""

from pathlib import Path

from dorje_lm.errors import LMConfigError
from dorje_lm.provider import LMProvider
from dorje_lm.providers.echo import EchoProvider
from dorje_lm.providers.pi.client import PiProvider
from dorje_lm.types import LMConfig


def create_lm_provider(config: LMConfig | None = None) -> LMProvider:
    """Create an LM provider from config."""
    resolved = config if config is not None else LMConfig()
    if resolved.provider == "echo":
        return EchoProvider()
    if resolved.provider == "pi":
        command = resolved.sidecar_command
        if command is None:
            command = _default_pi_sidecar_command()
        return PiProvider(command=command, model=resolved.model)
    raise LMConfigError(f"unsupported LM provider: {resolved.provider}")


def _default_pi_sidecar_command() -> tuple[str, ...]:
    root = Path(__file__).resolve().parents[2]
    sidecar = root / "sidecar" / "pi" / "index.mjs"
    if not sidecar.exists():
        raise LMConfigError(f"Pi sidecar not found: {sidecar}")
    return ("node", str(sidecar))
