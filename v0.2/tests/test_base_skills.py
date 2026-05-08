from pathlib import Path

from dorje.skills import load_skills


def test_summarize_wikipedia_page_skill_is_discoverable() -> None:
    root = Path(__file__).resolve().parents[1] / "base_skills"
    skills = load_skills(roots=(root,))

    assert "summarize_wikipedia_page" in skills
    assert "Wikipedia" in skills["summarize_wikipedia_page"].text
