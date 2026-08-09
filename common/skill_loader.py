"""
Shared skill-file loader. A SKILL.md has two parts:

  1. YAML frontmatter (between --- markers) — structured fields that
     DETERMINISTIC CODE needs directly (e.g. Feature Agent's entry-criteria
     WIQL fragment, which list_committed_features() must parse without any
     LLM involved).
  2. Markdown body — prose instructions the AGENT reads as part of its own
     context/system prompt (project-specific heuristics, quirks, section
     conventions).

This split exists because some consumers of a skill are plain Python
functions (need structured data) and some are LLM agents (want readable
instructions) — see the design discussion on why entry criteria live in
skills but the investigation process itself stays in code.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Skill:
    frontmatter: dict
    body: str
    path: Path


def load_skill(project_id: str, skill_name: str, skills_root: Path | str = None) -> Skill:
    """
    Loads skills/<project_id>/<skill_name>/SKILL.md

    Raises FileNotFoundError with a clear message if the project hasn't
    been onboarded yet (no Discovery Agent run) — this is a deliberate,
    loud failure rather than falling back to a silent default, since
    running Feature Agent against the wrong project's assumptions would
    be worse than refusing to run at all.
    """
    root = Path(skills_root) if skills_root else Path(__file__).parent.parent / "skills"
    skill_path = root / project_id / skill_name / "SKILL.md"

    if not skill_path.exists():
        raise FileNotFoundError(
            f"No skill found at {skill_path}. Run the Discovery Agent for project "
            f"'{project_id}' first to generate '{skill_name}' before using it."
        )

    raw = skill_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(raw)
    return Skill(frontmatter=frontmatter, body=body, path=skill_path)


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    _, fm_text, body = parts
    frontmatter = yaml.safe_load(fm_text) or {}
    return frontmatter, body.strip()


def write_skill(project_id: str, skill_name: str, frontmatter: dict, body: str, skills_root: Path | str = None) -> Path:
    """Writes a skill file — used by the Discovery Agent to persist a
    generated skill after the PM confirms it."""
    root = Path(skills_root) if skills_root else Path(__file__).parent.parent / "skills"
    skill_dir = root / project_id / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"

    fm_text = yaml.safe_dump(frontmatter, default_flow_style=False, sort_keys=False)
    content = f"---\n{fm_text}---\n\n{body}\n"
    skill_path.write_text(content, encoding="utf-8")
    return skill_path
