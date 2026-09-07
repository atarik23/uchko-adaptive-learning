from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from typing import Any, Optional

import pandas as pd
from django.conf import settings

from uchko_core.adaptive.policy import (
    AdaptiveDecision,
    SkillNode,
    choose_next_skill_and_difficulty,
)
from uchko_core.analytics.session_summaries import (
    summarize_session,
    upsert_session_summary,
)
from uchko_core.content.generator import generate_question
from uchko_core.content.load import load_skills, load_templates
from uchko_core.content.schemas import Question
from uchko_core.event_store import append_event, load_events
from uchko_core.events import (
    make_end_event,
    make_explanation_event,
    make_hint_event,
    make_solve_event,
    make_start_event,
)
from uchko_core.kt.mastery import init_mastery_state, recompute_mastery_from_events
from uchko_core.risk.features import extract_risk_features
from uchko_core.risk.model import score_risk, try_load_model
from uchko_core.risk.scoring import heuristic_risk_score, risk_level
from uchko_core.users import (
    get_or_create_user,
    load_users,
    update_user_prefs,
)


GOAL_MASTERY_THRESHOLD = 0.80
MIN_SOLVES_FOR_RISK = 5
RISK_THRESHOLD = 0.65


_SKILLS_CACHE: dict | None = None
_TEMPLATES_CACHE: list | None = None


def get_skills():
    global _SKILLS_CACHE
    if _SKILLS_CACHE is None:
        _SKILLS_CACHE = load_skills(settings.UCHKO_SKILLS_PATH)
    return _SKILLS_CACHE


def get_templates():
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is None:
        _TEMPLATES_CACHE = load_templates(settings.UCHKO_TEMPLATES_PATH)
    return _TEMPLATES_CACHE


def get_skill_nodes() -> dict[str, SkillNode]:
    skills = get_skills()
    return {
        sid: SkillNode(skill_id=sid, name=skills[sid].name, prerequisites=skills[sid].prerequisites)
        for sid in skills
    }


def get_skill_ids() -> list[str]:
    return list(get_skills().keys())


def format_skill_label(sid: str) -> str:
    skills = get_skills()
    return f"{sid} — {skills[sid].name}" if sid in skills else sid


def safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)

def initialize_authenticated_runtime_state(request) -> None:
    """
    Initializes the temporary runtime state used by the current learning flow.

    Authentication identity comes only from request.user. The session values
    are compatibility state for the existing dataset/event pipeline and will
    be replaced by persistent Django learning models in a later task.
    """
    if not request.user.is_authenticated:
        return

    s = request.session

    s["student_id"] = str(request.user.pk)
    s["username"] = request.user.username
    s["session_id"] = f"S_{uuid.uuid4().hex[:8]}"
    s["session_goal_skill_id"] = None
    s["session_start_mastery"] = {}

    reset_runtime_state(request)

    append_event(
        make_start_event(
            str(request.user.pk),
            s["session_id"],
        ),
        events_path=settings.UCHKO_EVENTS_PATH,
    )

    s.modified = True


def clear_authenticated_runtime_state(request) -> None:
    """
    Clears only temporary learning-session state before Django logout().
    """
    keys = [
        "student_id",
        "username",
        "session_id",
        "attempts",
        "current_q",
        "q_start_ts",
        "current_skill_id",
        "risk_smoothed",
        "session_goal_skill_id",
        "session_start_mastery",
        "adaptive_mode",
        "manual_skill_id",
        "manual_difficulty",
        "use_llm",
        "max_llm_calls",
        "llm_calls_used",
        "llm_used",
        "flash_messages",
    ]

    for key in keys:
        request.session.pop(key, None)

    request.session.modified = True

def ensure_state_defaults(request) -> None:
    s = request.session
    skill_ids = get_skill_ids()

    if request.user.is_authenticated:
        s["student_id"] = str(request.user.pk)
        s["username"] = request.user.username

    s.setdefault("session_id", f"S_{uuid.uuid4().hex[:8]}")

    s.setdefault("attempts", {})
    s.setdefault("current_q", None)
    s.setdefault("q_start_ts", None)
    s.setdefault("current_skill_id", None)
    s.setdefault("risk_smoothed", None)

    s.setdefault("session_goal_skill_id", None)
    s.setdefault("session_start_mastery", {})

    s.setdefault("adaptive_mode", True)
    s.setdefault("manual_skill_id", skill_ids[0] if skill_ids else None)
    s.setdefault("manual_difficulty", 1)

    s.setdefault("use_llm", False)
    s.setdefault("max_llm_calls", 0)
    s.setdefault("llm_calls_used", 0)
    s.setdefault("llm_used", False)

    s.setdefault("flash_messages", [])

    s.modified = True


def reset_runtime_state(request) -> None:
    s = request.session
    s["attempts"] = {}
    s["current_q"] = None
    s["q_start_ts"] = None
    s["current_skill_id"] = None
    s["risk_smoothed"] = None
    s["llm_calls_used"] = 0
    s["llm_used"] = False
    s.modified = True


def add_flash(request, message: str, level: str = "info") -> None:
    s = request.session
    msgs = list(s.get("flash_messages", []))
    msgs.append({"message": message, "level": level})
    s["flash_messages"] = msgs
    s.modified = True


def pop_flash_messages(request) -> list[dict]:
    msgs = list(request.session.get("flash_messages", []))
    request.session["flash_messages"] = []
    request.session.modified = True
    return msgs


def login_existing(request, username: str) -> None:
    users = load_users(settings.UCHKO_USERS_PATH)
    if username not in users:
        return
    user = users[username]
    request.session["username"] = user.username
    request.session["student_id"] = user.student_id
    request.session["session_id"] = f"S_{uuid.uuid4().hex[:8]}"
    request.session["session_goal_skill_id"] = None
    request.session["session_start_mastery"] = {}
    reset_runtime_state(request)
    append_event(
        make_start_event(user.student_id, request.session["session_id"]),
        events_path=settings.UCHKO_EVENTS_PATH,
    )


def create_and_login(request, username: str) -> None:
    user = get_or_create_user(settings.UCHKO_USERS_PATH, username)
    request.session["username"] = user.username
    request.session["student_id"] = user.student_id
    request.session["session_id"] = f"S_{uuid.uuid4().hex[:8]}"
    request.session["session_goal_skill_id"] = None
    request.session["session_start_mastery"] = {}
    reset_runtime_state(request)
    append_event(
        make_start_event(user.student_id, request.session["session_id"]),
        events_path=settings.UCHKO_EVENTS_PATH,
    )


def logout(request) -> None:
    keys = [
        "student_id", "username", "session_id", "attempts", "current_q",
        "q_start_ts", "current_skill_id", "risk_smoothed",
        "session_goal_skill_id", "session_start_mastery",
        "adaptive_mode", "manual_skill_id", "manual_difficulty",
        "use_llm", "max_llm_calls", "llm_calls_used", "llm_used",
    ]
    for k in keys:
        request.session.pop(k, None)
    request.session.modified = True


def is_logged_in(request) -> bool:
    return bool(request.session.get("student_id") and request.session.get("username"))


def start_new_session(request) -> None:
    sid = request.session.get("student_id")
    if not sid:
        return

    current_session = request.session.get("session_id")
    append_event(
        make_end_event(sid, current_session),
        events_path=settings.UCHKO_EVENTS_PATH,
    )

    try:
        df_all_u = load_events(settings.UCHKO_EVENTS_PATH, student_id=sid)
        df_sess = df_all_u[df_all_u["session_id"] == current_session].copy()

        row = summarize_session(
            repo_root=settings.UCHKO_REPO_ROOT,
            skills_path=settings.UCHKO_SKILLS_PATH,
            df_session=df_sess,
            student_id=sid,
            session_id=current_session,
            goal_skill_id=request.session.get("session_goal_skill_id"),
        )
        upsert_session_summary(out_path=settings.UCHKO_SESSION_SUMMARIES_PATH, row=row)
    except Exception as e:
        print("[WARN] Could not save session summary:", e)

    request.session["session_id"] = f"S_{uuid.uuid4().hex[:8]}"
    request.session["session_start_mastery"] = {}
    request.session["session_goal_skill_id"] = None
    reset_runtime_state(request)

    append_event(
        make_start_event(sid, request.session["session_id"]),
        events_path=settings.UCHKO_EVENTS_PATH,
    )


def end_session(request) -> None:
    sid = request.session.get("student_id")
    session_id = request.session.get("session_id")
    if not sid or not session_id:
        return

    append_event(
        make_end_event(sid, session_id),
        events_path=settings.UCHKO_EVENTS_PATH,
    )
    try:
        df_all_u = load_events(settings.UCHKO_EVENTS_PATH, student_id=sid)
        df_sess = df_all_u[df_all_u["session_id"] == session_id].copy()
        row = summarize_session(
            repo_root=settings.UCHKO_REPO_ROOT,
            skills_path=settings.UCHKO_SKILLS_PATH,
            df_session=df_sess,
            student_id=sid,
            session_id=session_id,
            goal_skill_id=request.session.get("session_goal_skill_id"),
        )
        upsert_session_summary(out_path=settings.UCHKO_SESSION_SUMMARIES_PATH, row=row)
        add_flash(request, "Session ended. Saved session summary.", level="success")
    except Exception as e:
        add_flash(request, f"Session ended, but could not save summary: {e}", level="warning")


def pick_goal_skill(skill_ids_: list[str], mastery_map_: dict) -> Optional[str]:
    if not skill_ids_:
        return None
    return min(skill_ids_, key=lambda sid: mastery_map_.get(sid, 0.0))


def session_metrics(df_session: pd.DataFrame) -> dict:
    if df_session is None or df_session.empty:
        return dict(n_events=0, n_solves=0, acc=0.0, mean_rt_ms=0.0, hints=0, expl=0)

    solves = df_session[df_session["event_type"] == "solve"]
    n_solves = int(len(solves))
    acc = float(solves["correct"].mean()) if n_solves and "correct" in solves.columns else 0.0
    mean_rt = float(solves["response_time_ms"].mean()) if n_solves and "response_time_ms" in solves.columns else 0.0
    hints = int((df_session["event_type"] == "hint").sum())
    expl = int((df_session["event_type"] == "explanation").sum())

    return dict(
        n_events=int(len(df_session)),
        n_solves=n_solves,
        acc=acc,
        mean_rt_ms=mean_rt,
        hints=hints,
        expl=expl,
    )


def chip_class_for_risk(risk_cat: str, ready: bool) -> str:
    if not ready:
        return "chip-warm"
    if risk_cat == "low":
        return "chip-low"
    if risk_cat == "medium":
        return "chip-med"
    if risk_cat == "high":
        return "chip-high"
    return "chip-warm"


def question_to_dict(q: Question) -> dict:
    return {
        "question_id": q.question_id,
        "skill_id": q.skill_id,
        "difficulty": int(q.difficulty),
        "type": q.type,
        "prompt": q.prompt,
        "correct_answer": q.correct_answer,
        "choices": list(q.choices) if q.choices else None,
        "template_id": q.template_id,
        "generated_params": dict(q.generated_params) if q.generated_params else {},
    }


def question_from_dict(d: dict) -> Question:
    return Question(
        question_id=d["question_id"],
        skill_id=d["skill_id"],
        difficulty=int(d["difficulty"]),
        type=d["type"],
        prompt=d["prompt"],
        correct_answer=d["correct_answer"],
        choices=d.get("choices"),
        template_id=d["template_id"],
        generated_params=d.get("generated_params", {}),
    )


def compute_app_state(request) -> dict:
    """Compute everything needed by views: events, mastery, risk, decision."""
    skills = get_skills()
    skill_ids = get_skill_ids()
    skill_nodes = get_skill_nodes()

    student_id = request.session.get("student_id")
    session_id = request.session.get("session_id")
    username = request.session.get("username")

    df_all = load_events(settings.UCHKO_EVENTS_PATH, student_id=student_id)
    if not df_all.empty and "session_id" in df_all.columns:
        df_session = df_all[df_all["session_id"] == session_id].copy()
    else:
        df_session = df_all.copy()

    metrics = session_metrics(df_session)

    mastery_state = recompute_mastery_from_events(df_session, skill_ids)
    mastery_map = mastery_state.mastery

    if request.session.get("session_goal_skill_id") is None:
        request.session["session_goal_skill_id"] = pick_goal_skill(skill_ids, mastery_map)
        request.session["session_start_mastery"] = dict(mastery_map)
        request.session.modified = True

    goal_skill_id = request.session["session_goal_skill_id"]

    if not request.session.get("session_start_mastery"):
        request.session["session_start_mastery"] = dict(mastery_map)
        request.session.modified = True

    goal_name = skills[goal_skill_id].name if goal_skill_id in skills else goal_skill_id
    start_m = safe_float(request.session["session_start_mastery"].get(goal_skill_id, 0.0))
    now_m = safe_float(mastery_map.get(goal_skill_id, 0.0))
    delta_m = now_m - start_m

    rf = extract_risk_features(df_session)
    risk_raw, risk_source, is_at_risk = score_risk(features=rf, repo_root=settings.UCHKO_REPO_ROOT)
    risk_flag = risk_raw >= RISK_THRESHOLD

    guard_reason = None
    n_solves = int(getattr(rf, "n_solves", 0))
    acc = float(getattr(rf, "acc", 0.0))

    use_model = (risk_source == "model")
    if use_model:
        if n_solves < 10 and float(risk_raw) > 0.90:
            use_model = False
            guard_reason = "Guard active: extreme risk during cold start."
        elif n_solves >= 10 and acc >= 0.80 and float(risk_raw) > 0.90:
            use_model = False
            guard_reason = "Guard active: extreme risk despite high accuracy."

    if not use_model:
        risk_raw = float(heuristic_risk_score(rf))
        risk_source = "heuristic (guarded)"

    if n_solves < MIN_SOLVES_FOR_RISK:
        risk_ready = False
        risk_score_used = None
        risk_cat = "warming_up"
    else:
        risk_ready = True
        smoothed = request.session.get("risk_smoothed")
        if smoothed is None:
            smoothed = float(risk_raw)
        else:
            if n_solves < 10:
                alpha = 0.55
            elif n_solves < 30:
                alpha = 0.30
            else:
                alpha = 0.18
            smoothed = (1 - alpha) * float(smoothed) + alpha * float(risk_raw)
        request.session["risk_smoothed"] = smoothed
        request.session.modified = True

        risk_score_used = float(smoothed)
        risk_cat = risk_level(risk_score_used)

    decision = choose_next_skill_and_difficulty(
        skills=skill_nodes,
        mastery=mastery_map,
        risk_score=risk_score_used if risk_ready else None,
        current_skill_id=request.session.get("current_skill_id"),
    )

    adaptive_mode = bool(request.session.get("adaptive_mode", True))

    chosen_skill_id = decision.skill_id
    chosen_difficulty = int(decision.difficulty)

    if adaptive_mode and mastery_map.get(goal_skill_id, 0.0) < GOAL_MASTERY_THRESHOLD:
        chosen_skill_id = goal_skill_id

    if not adaptive_mode:
        manual_skill = request.session.get("manual_skill_id") or skill_ids[0]
        chosen_skill_id = manual_skill
        chosen_difficulty = int(request.session.get("manual_difficulty", 1))

    request.session["current_skill_id"] = chosen_skill_id
    request.session.modified = True

    risk_label = "WARMING UP" if not risk_ready else risk_cat.upper()
    risk_css = chip_class_for_risk(risk_cat, risk_ready)

    return {
        "skills": skills,
        "skill_ids": skill_ids,
        "skill_nodes": skill_nodes,
        "username": username,
        "student_id": student_id,
        "session_id": session_id,
        "df_all": df_all,
        "df_session": df_session,
        "metrics": metrics,
        "mastery_state": mastery_state,
        "mastery_map": mastery_map,
        "goal_skill_id": goal_skill_id,
        "goal_name": goal_name,
        "goal_threshold": GOAL_MASTERY_THRESHOLD,
        "start_m": start_m,
        "now_m": now_m,
        "delta_m": delta_m,
        "rf": rf,
        "risk_raw": float(risk_raw),
        "risk_source": risk_source,
        "risk_ready": risk_ready,
        "risk_score_used": risk_score_used,
        "risk_cat": risk_cat,
        "risk_label": risk_label,
        "risk_css": risk_css,
        "guard_reason": guard_reason,
        "decision": decision,
        "adaptive_mode": adaptive_mode,
        "chosen_skill_id": chosen_skill_id,
        "chosen_difficulty": chosen_difficulty,
        "n_solves": n_solves,
        "min_solves_for_risk": MIN_SOLVES_FOR_RISK,
    }


def make_question(request, skill_id: str, difficulty: int) -> Question:
    skills = get_skills()
    templates = get_templates()
    s = request.session

    enable_llm_now = bool(s.get("use_llm")) and (
        int(s.get("llm_calls_used", 0)) < int(s.get("max_llm_calls", 0))
    )
    q = generate_question(
        templates,
        skill_id=skill_id,
        difficulty=int(difficulty),
        enable_llm=enable_llm_now,
        skill_name=skills[skill_id].name if skill_id in skills else skill_id,
    )
    s["current_q"] = question_to_dict(q)
    s["q_start_ts"] = time.time()
    attempts = dict(s.get("attempts", {}))
    attempts.setdefault(q.question_id, 0)
    s["attempts"] = attempts

    used = bool(getattr(q, "generated_params", {}).get("_llm_used", False))
    s["llm_used"] = used
    if used:
        s["llm_calls_used"] = int(s.get("llm_calls_used", 0)) + 1
    s.modified = True
    return q


def log_solve(request, q_dict: dict, is_correct: int) -> None:
    s = request.session
    student_id = s.get("student_id")
    session_id = s.get("session_id")

    attempts = dict(s.get("attempts", {}))
    attempts[q_dict["question_id"]] = attempts.get(q_dict["question_id"], 0) + 1
    attempt_number = attempts[q_dict["question_id"]]
    s["attempts"] = attempts

    start_ts = s.get("q_start_ts") or time.time()
    rt_ms = int((time.time() - float(start_ts)) * 1000)

    append_event(
        make_solve_event(
            student_id=student_id,
            session_id=session_id,
            skill_id=q_dict["skill_id"],
            question_id=q_dict["question_id"],
            difficulty=int(q_dict["difficulty"]),
            correct=int(is_correct),
            response_time_ms=int(rt_ms),
            attempt_number=int(attempt_number),
            meta={"template_id": q_dict["template_id"], "generated_params": q_dict["generated_params"]},
        ),
        events_path=settings.UCHKO_EVENTS_PATH,
    )
    s.modified = True


def log_hint(request, q_dict: dict, hint_text: str) -> None:
    s = request.session
    append_event(
        make_hint_event(
            student_id=s.get("student_id"),
            session_id=s.get("session_id"),
            skill_id=q_dict["skill_id"],
            question_id=q_dict["question_id"],
            difficulty=int(q_dict["difficulty"]),
            meta={"hint": hint_text},
        ),
        events_path=settings.UCHKO_EVENTS_PATH,
    )


def log_explanation(request, q_dict: dict, exp_text: str) -> None:
    s = request.session
    append_event(
        make_explanation_event(
            student_id=s.get("student_id"),
            session_id=s.get("session_id"),
            skill_id=q_dict["skill_id"],
            question_id=q_dict["question_id"],
            difficulty=int(q_dict["difficulty"]),
            meta={"explanation": exp_text},
        ),
        events_path=settings.UCHKO_EVENTS_PATH,
    )


def model_debug_info() -> dict:
    model_obj, feat_order, _thr = try_load_model(settings.UCHKO_REPO_ROOT)
    return {
        "loaded": model_obj is not None,
        "type": str(type(model_obj)) if model_obj is not None else None,
        "n_features": len(feat_order) if feat_order else 0,
        "features": list(feat_order) if feat_order else [],
    }


def list_users() -> list[str]:
    users = load_users(settings.UCHKO_USERS_PATH)
    return sorted(users.keys())


def save_goal_pref(username: str, goal_skill_id: str) -> None:
    update_user_prefs(settings.UCHKO_USERS_PATH, username, goal_skill_id=goal_skill_id)
