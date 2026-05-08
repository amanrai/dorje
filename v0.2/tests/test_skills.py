from pathlib import Path

from dorje.skills import default_skill_roots, load_skills


def test_default_roots_include_base_skills(tmp_path: Path) -> None:
    roots = default_skill_roots(cwd=tmp_path, home=tmp_path / "home")

    assert roots[0] == tmp_path / "base_skills"


def test_folder_skill_loading(tmp_path: Path) -> None:
    skill_dir = tmp_path / "detect_domain"
    skill_dir.mkdir()
    (skill_dir / "front-matter.yaml").write_text(
        "name: detect_domain\ndescription: Detect the information domain.\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text("Detect the domain.\n", encoding="utf-8")

    skills = load_skills(roots=(tmp_path,))

    assert skills["detect_domain"].description == "Detect the information domain."
    assert skills["detect_domain"].text == "Detect the domain.\n"
