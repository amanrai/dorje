import pytest

from dorje.agent_runtime import (
    AgentRequest,
    AgentRuntimeConfig,
    AgentRuntimeUnavailableError,
    create_agent_runtime,
)
from dorje.agent_runtime.runtimes.native import NativeAgentRuntime
from dorje.agent_runtime.runtimes.pi import PiAgentRuntime


def test_agent_runtime_factory_pi() -> None:
    runtime = create_agent_runtime(AgentRuntimeConfig(kind="pi"))

    try:
        assert isinstance(runtime, PiAgentRuntime)
    finally:
        runtime.close()


def test_agent_runtime_factory_native() -> None:
    runtime = create_agent_runtime(AgentRuntimeConfig(kind="native", lm_provider="echo"))

    try:
        assert isinstance(runtime, NativeAgentRuntime)
    finally:
        runtime.close()


def test_agent_runtime_placeholders_are_unavailable() -> None:
    runtime = create_agent_runtime(AgentRuntimeConfig(kind="native"))

    with pytest.raises(AgentRuntimeUnavailableError):
        runtime.run(AgentRequest(query="hello"))
