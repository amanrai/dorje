from dorje_lm import LMConfig, LMRequest, create_lm_provider


def test_echo_lm_provider() -> None:
    lm = create_lm_provider(LMConfig(provider="echo"))
    try:
        health = lm.health()
        response = lm.complete(LMRequest(prompt="hello"))
    finally:
        lm.close()

    assert health.ok is True
    assert health.provider == "echo"
    assert response.provider == "echo"
    assert response.text == "hello"
