from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BKTParams:
    """
    Classic Bayesian Knowledge Tracing parameters.
    p_init: P(L0) initial mastery
    p_transit: P(Lt -> Lt+1) learning probability after an opportunity
    p_guess: P(correct | not mastered)
    p_slip: P(incorrect | mastered)
    """
    p_init: float = 0.20
    p_transit: float = 0.12
    p_guess: float = 0.20
    p_slip: float = 0.10


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def posterior_mastery(p_mastery: float, correct: int, params: BKTParams) -> float:
    """
    Compute P(L | observation) before the learning transition step.

    correct=1: P(L|C) = (P(C|L)P(L)) / (P(C|L)P(L) + P(C|~L)P(~L))
    correct=0: similarly with incorrect likelihoods
    """
    pL = clamp01(p_mastery)

    if correct not in (0, 1):
        raise ValueError("correct must be 0 or 1")

    if correct == 1:
        p_obs_given_L = 1.0 - params.p_slip
        p_obs_given_notL = params.p_guess
    else:
        p_obs_given_L = params.p_slip
        p_obs_given_notL = 1.0 - params.p_guess

    num = p_obs_given_L * pL
    den = num + p_obs_given_notL * (1.0 - pL)

    # Avoid division by zero if params are extreme
    if den <= 0:
        return pL

    return clamp01(num / den)


def apply_learning_transition(p_mastery_post: float, params: BKTParams) -> float:
    """
    After observing an opportunity, mastery can increase:
    P(L_next) = P(L_post) + (1 - P(L_post)) * p_transit
    """
    p = clamp01(p_mastery_post)
    return clamp01(p + (1.0 - p) * params.p_transit)


def bkt_update(p_mastery: float, correct: int, params: BKTParams) -> float:
    """
    Full BKT update for one opportunity: posterior then learning transition.
    """
    post = posterior_mastery(p_mastery, correct, params)
    return apply_learning_transition(post, params)
