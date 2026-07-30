from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from uchko_core.adaptive.interventions import InterventionPlan

MASTERY_TO_PROGRESS = 0.80      # if current skill mastered, don't block progression
RISK_HIGH = 0.70
RISK_MED = 0.40


@dataclass(frozen=True)
class SkillNode:
    skill_id: str
    name: str
    prerequisites: List[str]


@dataclass(frozen=True)
class AdaptiveDecision:
    skill_id: str
    difficulty: int
    reason: str
    intervention: InterventionPlan


def _prereqs_mastered(skill: SkillNode, mastery: Dict[str, float], threshold: float) -> bool:
    for pre in skill.prerequisites:
        if mastery.get(pre, 0.0) < threshold:
            return False
    return True


def _unlocked_skills(skills: Dict[str, SkillNode], mastery: Dict[str, float], pre_threshold: float) -> List[str]:
    unlocked = []
    for sid, node in skills.items():
        if _prereqs_mastered(node, mastery, pre_threshold):
            unlocked.append(sid)
    return unlocked


def choose_next_skill_and_difficulty(
    skills: dict[str, SkillNode],
    mastery: dict[str, float],
    risk_score: float | None,
    current_skill_id: str | None,
) -> AdaptiveDecision:
    """
    Risk-aware policy:
      - Use mastery to pick weakest actionable skill
      - Use risk to adjust difficulty + consider prerequisites
      - Return an intervention plan for UI nudges

    risk_score can be None (minimum-evidence gate).
    """

    # ---- helpers ----
    def mastery_of(sid: str) -> float:
        return float(mastery.get(sid, 0.0))

    def prereqs(sid: str) -> list[str]:
        node = skills.get(sid)
        return list(node.prerequisites) if node else []

    # ---- choose candidate skill ----
    # Prefer current skill if it is still low mastery; otherwise pick lowest mastery overall.
    if current_skill_id and mastery_of(current_skill_id) < 0.75:
        base_skill = current_skill_id
    else:
        base_skill = min(skills.keys(), key=lambda s: mastery_of(s))

    base_mastery = mastery_of(base_skill)

    # ---- base difficulty from mastery ----
    # simple mapping
    if base_mastery < 0.40:
        base_diff = 1
    elif base_mastery < 0.75:
        base_diff = 2
    else:
        base_diff = 3

    # ---- risk-aware adjustments ----
    intervention = InterventionPlan(message="")

    if risk_score is None:
        # no evidence yet -> behave like mastery-only policy
        reason = f"Using mastery-only policy (risk warming up). Target skill={base_skill}."
        return AdaptiveDecision(
            skill_id=base_skill,
            difficulty=base_diff,
            reason=reason,
            intervention=intervention,
        )

    if risk_score >= RISK_HIGH:
        # If learner is already strong on the current/target skill, don't force prereqs.
        if base_mastery >= MASTERY_TO_PROGRESS:
            intervention = InterventionPlan(
                show_hint=False,
                show_explanation=False,
                message="High risk, but mastery is strong — allowing progression with caution.",
            )
            return AdaptiveDecision(
                skill_id=base_skill,
                difficulty=max(1, min(base_diff, 2)),  # avoid hardest when high-risk
                reason=f"High risk ({risk_score:.2f}) but mastery {base_mastery:.2f} ≥ {MASTERY_TO_PROGRESS:.2f}. No lockout.",
                intervention=intervention,
            )

        # Otherwise: step back, but only for a limited time (policy should not trap forever).
        pre = prereqs(base_skill)
        if pre:
            target = min(pre, key=lambda s: mastery_of(s))
            intervention = InterventionPlan(
                recommend_review_skill_id=target,
                show_hint=True,
                show_explanation=True,
                message="High risk: review prerequisite + scaffold.",
            )
            return AdaptiveDecision(
                skill_id=target,
                difficulty=1,
                reason=f"High risk ({risk_score:.2f}). Switching to prerequisite {target}.",
                intervention=intervention,
            )

        intervention = InterventionPlan(
            show_hint=True,
            show_explanation=True,
            message="High risk: lower difficulty + scaffold.",
        )
        return AdaptiveDecision(
            skill_id=base_skill,
            difficulty=1,
            reason=f"High risk ({risk_score:.2f}). Staying on {base_skill} but lowering difficulty.",
            intervention=intervention,
        )

    if risk_score >= 0.40:
        # Medium risk: keep skill, avoid escalating difficulty, suggest hint if mastery is low
        diff = min(base_diff, 2)
        intervention = InterventionPlan(
            show_hint=(base_mastery < 0.50),
            message="Medium risk: keep practicing, avoid jumping difficulty too fast.",
        )
        return AdaptiveDecision(
            skill_id=base_skill,
            difficulty=diff,
            reason=f"Medium risk ({risk_score:.2f}). Practice {base_skill} with controlled difficulty.",
            intervention=intervention,
        )

    # Low risk: allow challenge/progression
    # If mastery is high, move forward to a dependent skill if available (simple heuristic)
    diff = base_diff
    if base_mastery >= 0.80:
        diff = 3

    intervention = InterventionPlan(
        message="Low risk: you can handle more challenge.",
    )

    return AdaptiveDecision(
        skill_id=base_skill,
        difficulty=diff,
        reason=f"Low risk ({risk_score:.2f}). Continuing with mastery-driven selection.",
        intervention=intervention,
    )
