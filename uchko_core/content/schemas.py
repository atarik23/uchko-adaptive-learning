from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Literal, TypedDict

QuestionType = Literal["numeric", "mcq"]

@dataclass(frozen=True)
class Skill:
    skill_id: str
    name: str
    prerequisites: List[str]

class MCQSpec(TypedDict, total=False):
    choices: int
    distractors: List[str]

@dataclass(frozen=True)
class Template:
    template_id: str
    skill_id: str
    difficulty: int
    type: QuestionType
    prompt_template: str
    params: Dict[str, List[int]]
    answer_expr: str
    mcq: Optional[MCQSpec] = None

@dataclass
class Question:
    question_id: str
    skill_id: str
    difficulty: int
    type: QuestionType
    prompt: str
    correct_answer: str
    choices: Optional[List[str]]
    template_id: str
    generated_params: Dict[str, Any]
