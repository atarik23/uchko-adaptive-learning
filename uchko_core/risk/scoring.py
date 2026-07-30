from __future__ import annotations

from typing import Literal
import math

from .features import RiskFeatures


RiskLevel = Literal["low", "medium", "high"]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def heuristic_risk_score(f: RiskFeatures) -> float:
    """
    Baseline risk (0..1). Higher means higher risk.
    Designed for interpretability + stability in a demo.
    """
    # If almost no data, return "unknown moderate"
    if f.n_solves < 3:
        return 0.35

    # normalize slow responses: ~30s avg is considered very slow
    slow = min(1.0, f.mean_rt_ms / 30000.0) if f.mean_rt_ms > 0 else 0.0

    low_acc = 1.0 - f.acc
    low_recent = 1.0 - f.recent_acc_10
    streak = min(1.0, f.wrong_streak_max / 5.0)
    helpuse = min(1.0, (f.hints_per_solve + f.explanations_per_solve) / 2.0)

    # Weighted combination (tunable)
    z = (2.2 * low_acc) + (1.6 * low_recent) + (1.0 * slow) + (1.2 * streak) + (0.8 * helpuse) - 2.0
    return float(_sigmoid(z))


def risk_level(score: float) -> RiskLevel:
    if score >= 0.80:
        return "high"
    elif score >= 0.65:
        return "medium"
    else:
        return "low"
