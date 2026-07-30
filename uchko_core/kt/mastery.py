from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd
import json
from pathlib import Path

from .bkt import (
    BKTParams,
    posterior_mastery,
    apply_learning_transition,
    clamp01,
)


@dataclass
class MasteryState:
    """
    Holds mastery probabilities per skill_id.
    """
    mastery: Dict[str, float]
    params_by_skill: Dict[str, BKTParams]

    def get(self, skill_id: str) -> float:
        return float(self.mastery.get(skill_id, self.params_by_skill.get(skill_id, BKTParams()).p_init))

    def set(self, skill_id: str, value: float) -> None:
        self.mastery[skill_id] = clamp01(float(value))

    def update_from_solve(self, skill_id: str, correct: int, attempt_number: int = 1) -> float:
        params = self.params_by_skill.get(skill_id, BKTParams())
        prev = self.get(skill_id)

        # posterior update always
        post = posterior_mastery(prev, int(correct), params)

        # only learn on first attempt
        if int(attempt_number) <= 1:
            new = apply_learning_transition(post, params)
        else:
            new = post

        self.set(skill_id, new)
        return new


def default_params_for_skills(skill_ids: list[str], global_params: Optional[BKTParams] = None) -> Dict[str, BKTParams]:
    gp = global_params or BKTParams()
    return {sid: gp for sid in skill_ids}


def init_mastery_state(skill_ids: list[str], params_by_skill: Optional[Dict[str, BKTParams]] = None) -> MasteryState:
    if params_by_skill is None:
        repo_root = Path(__file__).resolve().parents[2]  # uchko_core/kt -> repo root
        gp = load_global_bkt_params(repo_root)
        params_by_skill = {sid: gp for sid in skill_ids}

    mastery = {sid: params_by_skill[sid].p_init for sid in skill_ids}
    return MasteryState(mastery=mastery, params_by_skill=params_by_skill)


def recompute_mastery_from_events(
    events_df: pd.DataFrame,
    skill_ids: list[str],
    params_by_skill: Optional[Dict[str, BKTParams]] = None,
) -> MasteryState:
    """
    Recompute mastery from scratch using the logged events (solve only).
    This prevents session-state drift and is great for debugging.
    """
    state = init_mastery_state(skill_ids, params_by_skill=params_by_skill)

    if events_df is None or len(events_df) == 0:
        return state

    df = events_df.copy()
    if "event_type" in df.columns:
        df = df[df["event_type"] == "solve"]

    # Sort by time to ensure correct sequence
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp", kind="mergesort")

    needed_cols = {"skill_id", "correct"}
    if not needed_cols.issubset(set(df.columns)):
        # If schema changes, fail loudly (better than silently wrong)
        missing = needed_cols - set(df.columns)
        raise ValueError(f"Events DF missing columns: {missing}")

    for _, row in df.iterrows():
        sid = str(row["skill_id"])
        if sid not in state.mastery:
            # ignore unknown skills
            continue
        c = int(row["correct"])

        # NEW: attempt-aware update
        attempt = int(row["attempt_number"]) if "attempt_number" in df.columns else 1
        state.update_from_solve(sid, c, attempt_number=attempt)

    return state

def load_global_bkt_params(repo_root: Path) -> BKTParams:
    path = repo_root / "models" / "bkt_params.json"
    if not path.exists():
        return BKTParams()

    payload = json.loads(path.read_text(encoding="utf-8"))
    g = payload.get("global_params", {})
    return BKTParams(
        p_init=float(g.get("p_init", BKTParams().p_init)),
        p_transit=float(g.get("p_transit", BKTParams().p_transit)),
        p_guess=float(g.get("p_guess", BKTParams().p_guess)),
        p_slip=float(g.get("p_slip", BKTParams().p_slip)),
    )