from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List

from .schemas import Skill, Template

def load_skills(skills_path: str | Path) -> Dict[str, Skill]:
    p = Path(skills_path)
    data = json.loads(p.read_text(encoding="utf-8"))
    skills: Dict[str, Skill] = {}
    for s in data["skills"]:
        skill = Skill(
            skill_id=s["skill_id"],
            name=s["name"],
            prerequisites=list(s.get("prerequisites", [])),
        )
        skills[skill.skill_id] = skill
    return skills

def load_templates(templates_path: str | Path) -> List[Template]:
    p = Path(templates_path)
    data = json.loads(p.read_text(encoding="utf-8"))
    templates: List[Template] = []
    for t in data["templates"]:
        templates.append(
            Template(
                template_id=t["template_id"],
                skill_id=t["skill_id"],
                difficulty=int(t["difficulty"]),
                type=t["type"],
                prompt_template=t["prompt_template"],
                params=t["params"],
                answer_expr=t["answer_expr"],
                mcq=t.get("mcq"),
            )
        )
    return templates
