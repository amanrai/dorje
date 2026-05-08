from pathlib import Path

from dorje.skills import load_skills


def test_fetch_wikipedia_page_skill_is_discoverable() -> None:
    root = Path(__file__).resolve().parents[1] / "base_skills"
    skills = load_skills(roots=(root,))

    assert "fetch_wikipedia_page" in skills
    assert "get_from_wikipedia" in skills["fetch_wikipedia_page"].text
