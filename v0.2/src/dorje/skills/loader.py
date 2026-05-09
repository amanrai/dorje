"""Prompt-only skill discovery and loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SKILL_FILE = "SKILL.md"
FRONT_MATTER_FILE = "front-matter.yaml"


@dataclass(frozen=True, slots=True)
class SkillSpec:
    """Loaded prompt-only skill."""

    name: str
    description: str
    text: str
    path: Path
    metadata: dict[str, Any] = field(default_factory=dict)


def default_skill_roots(cwd: Path | None = None, home: Path | None = None) -> tuple[Path, ...]:
    """Return skill roots in precedence order.

    Bundled/default skills come from the installed Dorje distribution, not the
    folder where ``dorje`` is invoked. Corpus-local skills live under
    ``./.dorje/skills``.
    """
    resolved_cwd = cwd if cwd is not None else Path.cwd()
    resolved_home = home if home is not None else Path.home()
    return (
        bundled_skill_root(),
        resolved_cwd / ".dorje" / "skills",
        resolved_home / ".dorje" / "skills",
    )


def bundled_skill_root() -> Path:
    """Return the bundled skill root for this Dorje install."""
    return Path(__file__).resolve().parents[3] / "base_skills"


def load_skills(roots: tuple[Path, ...] | None = None) -> dict[str, SkillSpec]:
    """Load skill folders from roots."""
    skill_roots = roots if roots is not None else default_skill_roots()
    skills: dict[str, SkillSpec] = {}
    seen: set[str] = set()

    for root in skill_roots:
        if not root.exists():
            continue
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            if folder.name in seen:
                continue
            skill_file = folder / SKILL_FILE
            if not skill_file.exists():
                continue
            spec = _load_skill(folder, skill_file)
            seen.add(spec.name)
            skills[spec.name] = spec

    return dict(sorted(skills.items()))


def _load_skill(folder: Path, skill_file: Path) -> SkillSpec:
    metadata = _load_metadata(folder / FRONT_MATTER_FILE)
    name_value = metadata.get("name", folder.name)
    description_value = metadata.get("description", "")
    if not isinstance(name_value, str) or len(name_value) == 0:
        raise ValueError(f"invalid skill name: {folder}")
    if not isinstance(description_value, str):
        raise ValueError(f"invalid skill description: {folder}")
    text = skill_file.read_text(encoding="utf-8")
    return SkillSpec(
        name=name_value,
        description=description_value,
        text=text,
        path=folder,
        metadata=metadata,
    )


def _load_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"front matter must be a mapping: {path}")
    return dict(loaded)
