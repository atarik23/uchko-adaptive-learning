from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd

from uchko_core.content.load import load_skills
from uchko_core.kt.mastery import recompute_mastery_from_events
from uchko_core.risk.features import extract_risk_features
from uchko_core.risk.model import score_risk
from uchko_core.risk.scoring import risk_level


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _session_basic_metrics(df_session: pd.DataFrame) -> Dict[str, Any]:
    if df_session is None or df_session.empty:
        return dict(n_events=0, n_solves=0, acc=0.0, mean_rt_ms=0.0, hints=0, explanations=0)

    solves = df_session[df_session["event_type"] == "solve"] if "event_type" in df_session.columns else df_session.iloc[0:0]
    n_solves = int(len(solves))
    acc = float(solves["correct"].mean()) if n_solves and "correct" in solves.columns else 0.0
    mean_rt = float(solves["response_time_ms"].mean()) if n_solves and "response_time_ms" in solves.columns else 0.0

    hints = int((df_session["event_type"] == "hint").sum()) if "event_type" in df_session.columns else 0
    explanations = int((df_session["event_type"] == "explanation").sum()) if "event_type" in df_session.columns else 0

    return dict(
        n_events=int(len(df_session)),
        n_solves=n_solves,
        acc=acc,
        mean_rt_ms=mean_rt,
        hints=hints,
        explanations=explanations,
    )


def summarize_session(
    *,
    repo_root: Path,
    skills_path: Path,
    df_session: pd.DataFrame,
    student_id: str,
    session_id: str,
    goal_skill_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Produce one summary row for a single session.
    """
    # timestamps
    if df_session is not None and (not df_session.empty) and ("timestamp" in df_session.columns):
        ts_min = _safe_float(df_session["timestamp"].min(), 0.0)
        ts_max = _safe_float(df_session["timestamp"].max(), 0.0)
    else:
        ts_min, ts_max = 0.0, 0.0

    duration_sec = max(0.0, ts_max - ts_min) if (ts_min and ts_max and ts_max >= ts_min) else 0.0

    # basic metrics
    m = _session_basic_metrics(df_session)

    # mastery snapshot
    skills = load_skills(skills_path)
    skill_ids = list(skills.keys())
    mastery_state = recompute_mastery_from_events(df_session, skill_ids)
    mastery_map = mastery_state.mastery  # dict skill->p

    mastery_vals = list(mastery_map.values()) if mastery_map else []
    mastery_mean = float(sum(mastery_vals) / len(mastery_vals)) if mastery_vals else 0.0
    mastery_min = float(min(mastery_vals)) if mastery_vals else 0.0
    mastery_goal = float(mastery_map.get(goal_skill_id, 0.0)) if goal_skill_id else None

    # strongest / weakest skills
    # (exclude skills that never appeared? optional; we keep all for now)
    sorted_sk = sorted(mastery_map.items(), key=lambda kv: kv[1])
    weak = sorted_sk[:3]
    strong = sorted_sk[-3:][::-1]

    # risk
    rf = extract_risk_features(df_session)
    risk_raw, risk_source, is_at_risk = score_risk(features=rf, repo_root=repo_root)

    # categorize risk using your existing thresholds
    risk_cat = risk_level(float(risk_raw))

    row = {
        "student_id": str(student_id),
        "session_id": str(session_id),
        "session_start_ts": float(ts_min),
        "session_end_ts": float(ts_max),
        "duration_sec": float(duration_sec),

        **m,

        "risk_raw": float(risk_raw),
        "risk_source": str(risk_source),
        "is_at_risk": None if is_at_risk is None else bool(is_at_risk),
        "risk_level": str(risk_cat),

        "goal_skill_id": str(goal_skill_id) if goal_skill_id else None,
        "mastery_mean": float(mastery_mean),
        "mastery_min": float(mastery_min),
        "mastery_goal": float(mastery_goal) if mastery_goal is not None else None,
        "mastery_json": json.dumps(mastery_map, ensure_ascii=False),
        "weak_skills_json": json.dumps(weak, ensure_ascii=False),
        "strong_skills_json": json.dumps(strong, ensure_ascii=False),

        "risk_features_json": json.dumps(asdict(rf), ensure_ascii=False),
    }
    return row


def upsert_session_summary(
    *,
    out_path: Path,
    row: Dict[str, Any],
) -> None:
    """
    Insert or replace a session summary row based on (student_id, session_id).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        df = pd.read_parquet(out_path)
    else:
        df = pd.DataFrame()

    new_row = pd.DataFrame([row])

    if not df.empty and {"student_id", "session_id"}.issubset(df.columns):
        mask = (df["student_id"] == row["student_id"]) & (df["session_id"] == row["session_id"])
        df = df.loc[~mask].copy()

    df = pd.concat([df, new_row], ignore_index=True)

    # nice ordering
    if "session_end_ts" in df.columns:
        df = df.sort_values(["student_id", "session_end_ts"], kind="mergesort")

    df.to_parquet(out_path, index=False)