from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


@dataclass
class RiskFeatures:
    n_solves: int
    n_correct: int
    acc: float

    mean_rt_ms: float
    p90_rt_ms: float

    wrong_streak_max: int
    recent_acc_10: float

    hints_per_solve: float
    explanations_per_solve: float

    #mean_difficulty: float

    def to_dict(self) -> Dict:
        return asdict(self)


FEATURE_ORDER: List[str] = [
    "n_solves",
    "acc",
    "recent_acc_10",
    "mean_rt_ms",
    "p90_rt_ms",
    "wrong_streak_max",
    "hints_per_solve",
    "explanations_per_solve",
    #"mean_difficulty",
]


def _max_wrong_streak(correct_series: pd.Series) -> int:
    max_streak = 0
    cur = 0
    for v in correct_series.fillna(1).astype(int).tolist():
        if v == 0:
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0
    return int(max_streak)


def extract_risk_features(events_df: pd.DataFrame) -> RiskFeatures:
    """
    Convert Uchko event log into abstract behavioral features for risk scoring.

    Expected event_type values: "solve", "hint", "explanation"
    Expected solve columns (if available): correct, response_time_ms, difficulty, timestamp
    """

    # --- empty / None guard ---
    if events_df is None or len(events_df) == 0:
        return RiskFeatures(
            n_solves=0, n_correct=0, acc=0.0,
            mean_rt_ms=0.0, p90_rt_ms=0.0,
            wrong_streak_max=0, recent_acc_10=0.0,
            hints_per_solve=0.0, explanations_per_solve=0.0,
            #mean_difficulty=0.0,
        )

    df = events_df.copy()

    # stable ordering for "recent" features
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp", kind="mergesort")

    # --- split event types ---
    if "event_type" in df.columns:
        solves = df[df["event_type"] == "solve"].copy()
        hints = df[df["event_type"] == "hint"].copy()
        expls = df[df["event_type"] == "explanation"].copy()
    else:
        solves = df.iloc[0:0].copy()
        hints = df.iloc[0:0].copy()
        expls = df.iloc[0:0].copy()


    n_solves = int(len(solves))
    if n_solves == 0:
        # no solves => cannot infer performance; keep rates at 0
        return RiskFeatures(
            n_solves=0, n_correct=0, acc=0.0,
            mean_rt_ms=0.0, p90_rt_ms=0.0,
            wrong_streak_max=0, recent_acc_10=0.0,
            hints_per_solve=0.0, explanations_per_solve=0.0,
            #mean_difficulty=0.0,
        )

    # --- correctness / accuracy ---
    if "correct" in solves.columns:
        correct = solves["correct"].fillna(0).astype(int)
    else:
        # if missing, assume unknown correctness -> treat as 0 to be conservative
        correct = pd.Series([0] * n_solves, index=solves.index, dtype=int)

    n_correct = int(correct.sum())
    acc = float(n_correct / n_solves) if n_solves else 0.0

    # --- response time stats (clipped) ---
    mean_rt_ms = 0.0
    p90_rt_ms = 0.0
    if "response_time_ms" in solves.columns:
        rt = (
            solves["response_time_ms"]
            .dropna()
            .astype(float)
            .clip(lower=0, upper=300_000)  # cap at 5 minutes
        )
        if len(rt) > 0:
            mean_rt_ms = float(rt.mean())
            p90_rt_ms = float(rt.quantile(0.9))

    # Match training transform: log1p on RT milliseconds
    mean_rt_ms = float(np.log1p(mean_rt_ms)) if mean_rt_ms > 0 else 0.0
    p90_rt_ms = float(np.log1p(p90_rt_ms)) if p90_rt_ms > 0 else 0.0
    # --- wrong streak ---
    wrong_streak_max = _max_wrong_streak(correct)

    # --- recent accuracy ---
    recent = correct.tail(10)
    recent_acc_10 = float(recent.mean()) if len(recent) else 0.0

    # --- help usage rates ---
    hints_per_solve = float(len(hints) / n_solves) if n_solves else 0.0
    explanations_per_solve = float(len(expls) / n_solves) if n_solves else 0.0

    return RiskFeatures(
        n_solves=n_solves,
        n_correct=n_correct,
        acc=acc,
        mean_rt_ms=mean_rt_ms,
        p90_rt_ms=p90_rt_ms,
        wrong_streak_max=wrong_streak_max,
        recent_acc_10=recent_acc_10,
        hints_per_solve=hints_per_solve,
        explanations_per_solve=explanations_per_solve,
        #mean_difficulty=mean_difficulty,
    )



def features_to_vector(f: RiskFeatures, order: Optional[List[str]] = None) -> np.ndarray:
    """
    Convert features to a numeric vector with a stable ordering.
    """
    order = order or FEATURE_ORDER
    d = f.to_dict()
    vec = np.array([float(d[k]) for k in order], dtype=float)
    return vec
