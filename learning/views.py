from __future__ import annotations

import io
import json
import random
from dataclasses import asdict

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.decorators import login_required

import pandas as pd

from uchko_core.content.skill_explanations import get_skill_explanations
from uchko_core.content.skill_hints import get_skill_hints

from . import services as svc


def _require_login(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    svc.ensure_state_defaults(request)
    return None


def account_view(request):
    """
    Legacy root route. It no longer lists or authenticates users.
    """
    if request.user.is_authenticated:
        return redirect("learning:practice")

    return redirect("accounts:login")


def create_user_view(request):
    """
    Legacy endpoint retained only for backwards-compatible links.
    Public registration now lives at /accounts/register/.
    """
    return redirect("accounts:register")


def select_user_view(request):
    """
    Legacy endpoint intentionally does not authenticate a selected username.
    """
    return redirect("accounts:login")


def logout_view(request):
    """
    Legacy endpoint redirects to the Django-auth logout endpoint.
    """
    return redirect("accounts:logout")

@login_required
@require_POST
def new_session_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    svc.start_new_session(request)
    svc.add_flash(request, "Started a new session.", level="info")
    return redirect("learning:practice")

@login_required
@require_POST
def end_session_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    svc.end_session(request)
    return redirect("learning:practice")


def _build_top_context(request, state: dict) -> dict:
    return {
        "username": state["username"],
        "session_id": state["session_id"],
        "metrics": state["metrics"],
        "risk_label": state["risk_label"],
        "risk_css": state["risk_css"],
        "goal_name": state["goal_name"],
        "goal_threshold": state["goal_threshold"],
        "now_m": state["now_m"],
        "skills": state["skills"],
        "skill_ids": state["skill_ids"],
    }

@login_required
def practice_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    state = svc.compute_app_state(request)

    s = request.session
    chosen_skill_id = state["chosen_skill_id"]
    chosen_difficulty = state["chosen_difficulty"]
    decision = state["decision"]
    skills = state["skills"]
    selected_skill_name = skills[chosen_skill_id].name if chosen_skill_id in skills else chosen_skill_id

    interv = decision.intervention
    review_skill_name = None
    if interv.recommend_review_skill_id and interv.recommend_review_skill_id in skills:
        review_skill_name = skills[interv.recommend_review_skill_id].name

    progress_value = 0.0
    denom = max(1e-6, state["goal_threshold"] - state["start_m"])
    progress_value = max(0.0, min(1.0, (state["now_m"] - state["start_m"]) / denom)) * 100.0

    current_q = s.get("current_q")

    skill_options = [{"id": sid, "label": svc.format_skill_label(sid)} for sid in state["skill_ids"]]

    context = {
        **_build_top_context(request, state),
        "active_tab": "practice",
        "chosen_skill_id": chosen_skill_id,
        "chosen_skill_name": selected_skill_name,
        "chosen_difficulty": chosen_difficulty,
        "decision_reason": decision.reason if state["adaptive_mode"] else "Manual selection.",
        "intervention_message": interv.message,
        "review_skill_id": interv.recommend_review_skill_id,
        "review_skill_name": review_skill_name,
        "risk_source": state["risk_source"],
        "risk_raw": state["risk_raw"],
        "risk_score_used": state["risk_score_used"],
        "risk_ready": state["risk_ready"],
        "guard_reason": state["guard_reason"],
        "adaptive_mode": state["adaptive_mode"],
        "manual_skill_id": s.get("manual_skill_id"),
        "manual_difficulty": s.get("manual_difficulty"),
        "skill_options": skill_options,
        "difficulty_options": [1, 2, 3],
        "goal_skill_id": state["goal_skill_id"],
        "start_m": state["start_m"],
        "delta_m": state["delta_m"],
        "progress_value": progress_value,
        "current_q": current_q,
        "llm_used": s.get("llm_used", False),
        "goal_reached": state["now_m"] >= state["goal_threshold"],
        "flash_messages": svc.pop_flash_messages(request),
    }
    return render(request, "learning/practice.html", context)

@login_required
@require_POST
def generate_question_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    state = svc.compute_app_state(request)
    svc.make_question(request, state["chosen_skill_id"], state["chosen_difficulty"])
    return redirect("learning:practice")

@login_required
@require_POST
def submit_answer_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    s = request.session
    current_q = s.get("current_q")
    if not current_q:
        svc.add_flash(request, "No active question. Please generate one.", level="warning")
        return redirect("learning:practice")

    user_answer = (request.POST.get("answer") or "").strip()
    correct_answer = str(current_q.get("correct_answer", "")).strip()

    if current_q.get("type") == "mcq":
        is_correct = int(user_answer == correct_answer)
    else:
        is_correct = int(user_answer == correct_answer)

    svc.log_solve(request, current_q, is_correct)

    if is_correct:
        svc.add_flash(request, "✅ Correct!", level="success")
    else:
        svc.add_flash(request, f"❌ Incorrect. Correct answer: {correct_answer}", level="error")

    state = svc.compute_app_state(request)
    svc.make_question(request, state["chosen_skill_id"], state["chosen_difficulty"])
    return redirect("learning:practice")

@login_required
@require_POST
def request_hint_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    current_q = request.session.get("current_q")
    if not current_q:
        return redirect("learning:practice")
    hints = get_skill_hints(current_q["skill_id"], n=3)
    hint_text = random.choice(hints) if hints else "Try breaking the problem into smaller steps."
    svc.log_hint(request, current_q, hint_text)
    svc.add_flash(request, f"Hint: {hint_text}", level="info")
    return redirect("learning:practice")

@login_required
@require_POST
def request_explanation_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    current_q = request.session.get("current_q")
    if not current_q:
        return redirect("learning:practice")
    exps = get_skill_explanations(current_q["skill_id"], n=3)
    exp_text = random.choice(exps) if exps else "Think about the rule being applied and work step-by-step."
    svc.log_explanation(request, current_q, exp_text)
    svc.add_flash(request, f"Explanation: {exp_text}", level="info")
    return redirect("learning:practice")

@login_required
@require_POST
def set_goal_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    s = request.session
    new_goal = request.POST.get("goal_skill_id")
    if not new_goal or new_goal not in svc.get_skill_ids():
        svc.add_flash(request, "Invalid goal skill.", level="error")
        return redirect("learning:practice")

    state = svc.compute_app_state(request)
    s["session_goal_skill_id"] = new_goal
    s["session_start_mastery"] = dict(state["mastery_map"])
    s["current_q"] = None
    s["q_start_ts"] = None
    s["current_skill_id"] = None
    s.modified = True

    if s.get("username"):
        try:
            svc.save_goal_pref(s["username"], new_goal)
        except Exception:
            pass

    svc.add_flash(request, "Goal updated. Generate a new question to start practicing it.", level="success")
    return redirect("learning:practice")

@login_required
@require_POST
def toggle_adaptive_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    new_val = request.POST.get("adaptive_mode") == "on"
    request.session["adaptive_mode"] = new_val
    request.session.modified = True
    return redirect("learning:practice")

@login_required
@require_POST
def set_manual_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    s = request.session
    sid = request.POST.get("manual_skill_id")
    diff = request.POST.get("manual_difficulty")
    if sid and sid in svc.get_skill_ids():
        s["manual_skill_id"] = sid
    if diff:
        try:
            d = int(diff)
            if d in (1, 2, 3):
                s["manual_difficulty"] = d
        except Exception:
            pass
    s.modified = True
    return redirect("learning:practice")

@login_required
def progress_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    state = svc.compute_app_state(request)

    rows = []
    for sid in state["skill_ids"]:
        prereqs = getattr(state["skills"][sid], "prerequisites", []) or []
        rows.append({
            "skill_id": sid,
            "skill": state["skills"][sid].name,
            "mastery": float(state["mastery_map"].get(sid, 0.0)),
            "prerequisites": ", ".join(prereqs),
        })
    rows.sort(key=lambda r: r["mastery"])

    metrics = state["metrics"]
    avg_rt_seconds = (metrics["mean_rt_ms"] / 1000.0) if metrics["mean_rt_ms"] > 0 else None

    context = {
        **_build_top_context(request, state),
        "active_tab": "progress",
        "mastery_rows": rows,
        "avg_rt_seconds": avg_rt_seconds,
        "risk_ready": state["risk_ready"],
        "risk_score_used": state["risk_score_used"],
        "risk_cat": state["risk_cat"],
        "risk_source": state["risk_source"],
        "guard_reason": state["guard_reason"],
        "n_solves": state["n_solves"],
        "min_solves_for_risk": state["min_solves_for_risk"],
        "flash_messages": svc.pop_flash_messages(request),
    }
    return render(request, "learning/progress.html", context)

@login_required
def curriculum_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    state = svc.compute_app_state(request)
    skills = state["skills"]
    skill_ids = state["skill_ids"]

    selected_sid = request.GET.get("skill") or skill_ids[0]
    if selected_sid not in skills:
        selected_sid = skill_ids[0]

    prereqs = getattr(skills[selected_sid], "prerequisites", []) or []
    prereq_rows = []
    for p in prereqs:
        prereq_rows.append({
            "id": p,
            "name": skills[p].name if p in skills else p,
            "mastery": float(state["mastery_map"].get(p, 0.0)),
        })

    skill_options = [{"id": sid, "label": svc.format_skill_label(sid)} for sid in skill_ids]

    context = {
        **_build_top_context(request, state),
        "active_tab": "curriculum",
        "selected_skill_id": selected_sid,
        "selected_skill_name": skills[selected_sid].name,
        "prereq_rows": prereq_rows,
        "skill_options": skill_options,
        "flash_messages": svc.pop_flash_messages(request),
    }
    return render(request, "learning/curriculum.html", context)

@login_required
def curriculum_graph_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    state = svc.compute_app_state(request)

    try:
        import matplotlib
        matplotlib.use("Agg")
        from uchko_core.viz.curriculum_graph import draw_curriculum_graph

        fig = draw_curriculum_graph(
            skills=state["skills"],
            mastery=state["mastery_map"],
            goal_skill_id=state["goal_skill_id"],
            recommended_skill_id=state["chosen_skill_id"],
            figsize=(12, 7),
        )
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        import matplotlib.pyplot as plt
        plt.close(fig)
        buf.seek(0)
        return HttpResponse(buf.getvalue(), content_type="image/png")
    except Exception as e:
        return HttpResponse(f"Could not render curriculum graph: {e}", status=500, content_type="text/plain")

@login_required
def settings_view(request):
    redir = _require_login(request)
    if redir:
        return redir
    state = svc.compute_app_state(request)

    df_user = pd.DataFrame()
    if settings.UCHKO_SESSION_SUMMARIES_PATH.exists():
        try:
            df_hist = pd.read_parquet(settings.UCHKO_SESSION_SUMMARIES_PATH)
            df_user = df_hist[df_hist["student_id"] == state["student_id"]].copy()
            if not df_user.empty:
                df_user = df_user.sort_values("session_end_ts", ascending=False)
        except Exception:
            df_user = pd.DataFrame()

    history_rows = []
    weak_rows = []
    strong_rows = []
    if not df_user.empty:
        keep_cols = ["session_id", "session_end_ts", "n_solves", "acc", "risk_raw", "risk_level", "mastery_goal"]
        for _, r in df_user.iterrows():
            history_rows.append({
                "session_id": r.get("session_id", ""),
                "session_end_ts": r.get("session_end_ts", 0.0),
                "n_solves": int(r.get("n_solves", 0) or 0),
                "acc": float(r.get("acc", 0.0) or 0.0),
                "risk_raw": float(r.get("risk_raw", 0.0) or 0.0),
                "risk_level": r.get("risk_level", ""),
                "mastery_goal": r.get("mastery_goal"),
            })

        latest = df_user.iloc[0]
        try:
            weak = json.loads(latest.get("weak_skills_json", "[]"))
        except Exception:
            weak = []
        try:
            strong = json.loads(latest.get("strong_skills_json", "[]"))
        except Exception:
            strong = []
        for sid, p in weak:
            weak_rows.append({
                "id": sid,
                "name": state["skills"][sid].name if sid in state["skills"] else sid,
                "mastery": float(p),
            })
        for sid, p in strong:
            strong_rows.append({
                "id": sid,
                "name": state["skills"][sid].name if sid in state["skills"] else sid,
                "mastery": float(p),
            })

    df_session_records = []
    df_all_records = []
    if state["df_session"] is not None and not state["df_session"].empty:
        df_session_records = state["df_session"].fillna("").to_dict("records")
    if state["df_all"] is not None and not state["df_all"].empty:
        df_all_records = state["df_all"].fillna("").to_dict("records")

    rf_dict = asdict(state["rf"])
    model_info = svc.model_debug_info()

    context = {
        **_build_top_context(request, state),
        "active_tab": "settings",
        "history_rows": history_rows,
        "weak_rows": weak_rows,
        "strong_rows": strong_rows,
        "adaptive_mode": state["adaptive_mode"],
        "manual_skill_label": svc.format_skill_label(request.session.get("manual_skill_id") or ""),
        "manual_difficulty": request.session.get("manual_difficulty"),
        "risk_source": state["risk_source"],
        "risk_raw": state["risk_raw"],
        "risk_score_used": state["risk_score_used"],
        "risk_ready": state["risk_ready"],
        "guard_reason": state["guard_reason"],
        "rf_dict": rf_dict,
        "model_info": model_info,
        "session_events": df_session_records,
        "all_events": df_all_records,
        "flash_messages": svc.pop_flash_messages(request),
    }
    return render(request, "learning/settings.html", context)

@login_required
def export_session_csv(request):
    redir = _require_login(request)
    if redir:
        return redir
    state = svc.compute_app_state(request)
    df = state["df_session"]
    if df is None or df.empty:
        df = pd.DataFrame()
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    filename = f"uchko_events_{state['student_id']}_{state['session_id']}.csv"
    response = HttpResponse(csv_bytes, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
