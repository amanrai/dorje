"""Pi SDK-backed agent runtime."""

from pathlib import Path
from typing import Any

from dorje.agent_runtime.errors import AgentRuntimeError
from dorje.agent_runtime.types import AgentRequest, AgentResponse
from dorje.extensions import load_extensions
from dorje_lm.providers.pi.sidecar import SidecarProcess
from dorje.skills import load_skills


class PiAgentRuntime:
    """Agent runtime that delegates to the Pi SDK native tool loop."""

    def __init__(self, model: str | None = None, command: tuple[str, ...] | None = None) -> None:
        self._model = model
        self._sidecar = SidecarProcess(command or _default_command(), cwd=Path.cwd())

    def run(self, request: AgentRequest) -> AgentResponse:
        registry = load_extensions()
        skills = load_skills()
        requested_skills = _select_skills(skills, request.skill_names)
        payload: dict[str, Any] = {
            "op": "run",
            "query": request.query,
            "cwd": str(Path.cwd()),
            "model": self._model,
            "skill_names": [skill.name for skill in requested_skills],
            "skills_text": _format_skills(requested_skills),
            "tools": [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "extension_name": spec.extension_name,
                }
                for spec in registry.list()
            ],
            "context": request.context,
        }
        response = self._sidecar.request(payload, timeout_s=300.0)
        if response.get("ok") is not True:
            error = response.get("error")
            raise AgentRuntimeError(error if isinstance(error, str) else "Pi agent runtime failed")
        content = response.get("content")
        if not isinstance(content, str):
            raise AgentRuntimeError("Pi agent runtime response missing content")
        return AgentResponse(content=content, runtime="pi", raw=response)

    def close(self) -> None:
        self._sidecar.close()


def _default_command() -> tuple[str, ...]:
    root = Path(__file__).resolve().parents[4]
    sidecar = root / "sidecar" / "pi" / "agent.mjs"
    if not sidecar.exists():
        raise AgentRuntimeError(f"Pi agent sidecar not found: {sidecar}")
    return ("node", str(sidecar))


def _select_skills(skills: dict[str, Any], names: tuple[str, ...]) -> tuple[Any, ...]:
    if len(names) == 0:
        return tuple(skills.values())
    missing = [name for name in names if name not in skills]
    if missing:
        raise AgentRuntimeError(f"unknown skills: {', '.join(missing)}")
    return tuple(skills[name] for name in names)


def _format_skills(skills: tuple[Any, ...]) -> str:
    blocks = []
    for skill in skills:
        blocks.append(f"## {skill.name}\n\n{skill.text.strip()}")
    return "\n\n".join(blocks)
