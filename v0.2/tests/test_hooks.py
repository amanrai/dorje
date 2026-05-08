from pathlib import Path


def test_lifecycle_hook_scripts_exist() -> None:
    root = Path(__file__).resolve().parents[1] / "hooks"

    for name in (
        "start_agent",
        "pre_skill_use",
        "pre_tool_call",
        "post_tool_call",
        "post_skill_use",
        "end_agent",
    ):
        script = root / f"{name}.mjs"
        assert script.exists()
        assert f"This is the {name} hook being fired" in script.read_text(encoding="utf-8")
