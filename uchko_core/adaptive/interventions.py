from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InterventionPlan:
    """
    What the system recommends doing right now.
    Keep it simple and explainable for the demo.
    """
    show_hint: bool = False
    show_explanation: bool = False
    recommend_review_skill_id: Optional[str] = None
    message: str = ""
