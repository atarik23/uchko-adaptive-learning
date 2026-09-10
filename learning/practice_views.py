from __future__ import annotations

import time

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import student_required
from courses.models import (
    LearningItem,
    LearningSession,
    StudentKnowledgeState,
)

from .adaptive_service import (
    DATASET_NAME,
    get_or_create_active_session,
    get_student_enrollment,
    record_learning_attempt,
    select_next_learning_item,
)

from .content_sanitizer import sanitize_learning_html


CURRENT_ITEM_ID = "adaptive_current_item_id"
CURRENT_STARTED_AT = "adaptive_current_started_at"
CURRENT_HINT_COUNT = "adaptive_current_hint_count"
CURRENT_SAW_ANSWER = "adaptive_current_saw_answer"
CURRENT_SUCCESS_PROBABILITY = (
    "adaptive_current_success_probability"
)
CURRENT_SELECTION_REASON = "adaptive_current_selection_reason"
CURRENT_BKT_SOURCE = "adaptive_current_bkt_source"
CURRENT_MASTERY = "adaptive_current_mastery"
LAST_RESULT = "adaptive_last_result"


def _clear_current_question(request) -> None:
    keys = [
        CURRENT_ITEM_ID,
        CURRENT_STARTED_AT,
        CURRENT_HINT_COUNT,
        CURRENT_SAW_ANSWER,
        CURRENT_SUCCESS_PROBABILITY,
        CURRENT_SELECTION_REASON,
        CURRENT_BKT_SOURCE,
        CURRENT_MASTERY,
    ]

    for key in keys:
        request.session.pop(key, None)

    request.session.modified = True


def _store_selection(request, selection) -> None:
    request.session[CURRENT_ITEM_ID] = (
        selection.learning_item.id
    )
    request.session[CURRENT_STARTED_AT] = time.time()
    request.session[CURRENT_HINT_COUNT] = 0
    request.session[CURRENT_SAW_ANSWER] = False
    request.session[CURRENT_SUCCESS_PROBABILITY] = float(
        selection.success_probability
    )
    request.session[CURRENT_SELECTION_REASON] = (
        selection.reason
    )
    request.session[CURRENT_BKT_SOURCE] = (
        selection.bkt_source
    )
    request.session[CURRENT_MASTERY] = float(
        selection.mastery_probability
    )
    request.session.modified = True


def _get_current_item(request, enrollment):
    item_id = request.session.get(CURRENT_ITEM_ID)

    if item_id is None:
        return None

    item = (
        LearningItem.objects
        .filter(
            id=item_id,
            course=enrollment.course,
            is_active=True,
            source_dataset=DATASET_NAME,
        )
        .select_related(
            "primary_knowledge_component",
        )
        .first()
    )

    if item is None:
        _clear_current_question(request)

    return item


def _response_time_ms(request) -> int:
    started_at = request.session.get(
        CURRENT_STARTED_AT
    )

    if started_at is None:
        return 0

    try:
        elapsed_seconds = (
            time.time() - float(started_at)
        )
    except (TypeError, ValueError):
        return 0

    return max(
        int(elapsed_seconds * 1000),
        0,
    )


def _choice_rows(item) -> list[dict]:
    if item is None:
        return []

    if (
        item.problem_type
        != "Multiple Choice (select 1)"
        or item.answer_type != "Multiple Choice"
    ):
        return []

    return [
        {
            "index": index,
            "html": sanitize_learning_html(option),
        }
        for index, option in enumerate(
            item.multiple_choice_options
        )
    ]


@student_required
def practice_view(request):
    try:
        enrollment = get_student_enrollment(
            request.user
        )
    except ValueError as error:
        return render(
            request,
            "learning/practice.html",
            {
                "active_tab": "practice",
                "setup_error": str(error),
                "current_item": None,
            },
        )

    current_item = _get_current_item(
        request,
        enrollment,
    )

    current_component = (
        current_item.primary_knowledge_component
        if current_item is not None
        else None
    )

    knowledge_state = None

    if current_component is not None:
        knowledge_state = (
            StudentKnowledgeState.objects
            .filter(
                enrollment=enrollment,
                knowledge_component=current_component,
            )
            .first()
        )

    last_result = request.session.pop(
        LAST_RESULT,
        None,
    )

    if last_result is not None:
        request.session.modified = True

    context = {
        "active_tab": "practice",
        "enrollment": enrollment,
        "course": enrollment.course,
        "current_item": current_item,
        "current_item_body_html": (
            sanitize_learning_html(current_item.body)
            if current_item is not None
            else ""
        ),
        "current_component": current_component,
        "choice_rows": _choice_rows(
            current_item
        ),
        "hint_count": request.session.get(
            CURRENT_HINT_COUNT,
            0,
        ),
        "selection_reason": request.session.get(
            CURRENT_SELECTION_REASON,
            "",
        ),
        "bkt_source": request.session.get(
            CURRENT_BKT_SOURCE,
            "",
        ),
        "selection_mastery": request.session.get(
            CURRENT_MASTERY,
        ),
        "success_probability": (
            request.session.get(
                CURRENT_SUCCESS_PROBABILITY,
            )
        ),
        "knowledge_state": knowledge_state,
        "last_result": last_result,
    }

    return render(
        request,
        "learning/practice.html",
        context,
    )


@student_required
@require_POST
def generate_question_view(request):
    try:
        enrollment = get_student_enrollment(
            request.user
        )
        selection = select_next_learning_item(
            enrollment
        )
    except ValueError as error:
        messages.error(
            request,
            str(error),
        )
        return redirect("learning:practice")

    get_or_create_active_session(
        enrollment=enrollment,
        goal_component=(
            selection.knowledge_component
        ),
    )

    _store_selection(
        request,
        selection,
    )

    return redirect("learning:practice")


@student_required
@require_POST
def submit_answer_view(request):
    try:
        enrollment = get_student_enrollment(
            request.user
        )
    except ValueError as error:
        messages.error(
            request,
            str(error),
        )
        return redirect("learning:practice")

    item = _get_current_item(
        request,
        enrollment,
    )

    if item is None:
        messages.warning(
            request,
            "There is no active question.",
        )
        return redirect("learning:practice")

    submitted_answer = (
        request.POST.get("answer") or ""
    ).strip()

    if not submitted_answer:
        messages.warning(
            request,
            "Please provide an answer.",
        )
        return redirect("learning:practice")

    result = record_learning_attempt(
        enrollment=enrollment,
        learning_item=item,
        submitted_answer=submitted_answer,
        response_time_ms=_response_time_ms(
            request
        ),
        hint_count=request.session.get(
            CURRENT_HINT_COUNT,
            0,
        ),
        saw_answer=request.session.get(
            CURRENT_SAW_ANSWER,
            False,
        ),
        predicted_success_probability=(
            request.session.get(
                CURRENT_SUCCESS_PROBABILITY,
            )
        ),
    )

    request.session[LAST_RESULT] = {
        "answer_is_correct": (
            result.answer_is_correct
        ),
        "independent_success": (
            result.independent_success
        ),
        "previous_mastery": float(
            result.previous_mastery
        ),
        "updated_mastery": float(
            result.updated_mastery
        ),
        "skill_code": (
            result.attempt
            .knowledge_component
            .external_id
        ),
        "skill_name": (
            result.attempt
            .knowledge_component
            .name
        ),
        "attempt_number": (
            result.attempt.attempt_number
        ),
    }

    _clear_current_question(request)

    if result.answer_is_correct:
        messages.success(
            request,
            "Correct answer!",
        )
    else:
        messages.error(
            request,
            "The answer is not correct.",
        )

    return redirect("learning:practice")


@student_required
@require_POST
def request_hint_view(request):
    try:
        enrollment = get_student_enrollment(
            request.user
        )
    except ValueError as error:
        messages.error(
            request,
            str(error),
        )
        return redirect("learning:practice")

    item = _get_current_item(
        request,
        enrollment,
    )

    if item is None:
        messages.warning(
            request,
            "There is no active question.",
        )
        return redirect("learning:practice")

    hint_count = int(
        request.session.get(
            CURRENT_HINT_COUNT,
            0,
        )
    )
    request.session[CURRENT_HINT_COUNT] = (
        hint_count + 1
    )
    request.session.modified = True

    component = (
        item.primary_knowledge_component
    )

    if (
        component is not None
        and component.description
    ):
        hint_text = component.description
    elif component is not None:
        hint_text = (
            f"Review the concept: {component.name}."
        )
    else:
        hint_text = (
            "Break the problem into smaller steps "
            "and check each operation."
        )

    messages.info(
        request,
        f"Hint: {hint_text}",
    )

    return redirect("learning:practice")


@student_required
@require_POST
def request_explanation_view(request):
    messages.info(
        request,
        (
            "A detailed explanation is available "
            "after the answer is submitted."
        ),
    )

    return redirect("learning:practice")


@student_required
@require_POST
def new_session_view(request):
    try:
        enrollment = get_student_enrollment(
            request.user
        )
    except ValueError as error:
        messages.error(
            request,
            str(error),
        )
        return redirect("learning:practice")

    active_sessions = (
        LearningSession.objects
        .filter(
            enrollment=enrollment,
            is_active=True,
            ended_at=None,
        )
    )

    for session in active_sessions:
        session.ended_at = timezone.now()
        session.is_active = False
        session.save()

    _clear_current_question(request)

    get_or_create_active_session(
        enrollment=enrollment
    )

    messages.success(
        request,
        "A new learning session has started.",
    )

    return redirect("learning:practice")


@student_required
@require_POST
def end_session_view(request):
    try:
        enrollment = get_student_enrollment(
            request.user
        )
    except ValueError as error:
        messages.error(
            request,
            str(error),
        )
        return redirect("learning:practice")

    active_sessions = (
        LearningSession.objects
        .filter(
            enrollment=enrollment,
            is_active=True,
            ended_at=None,
        )
    )

    ended_count = 0

    for session in active_sessions:
        session.ended_at = timezone.now()
        session.is_active = False
        session.save()
        ended_count += 1

    _clear_current_question(request)

    if ended_count:
        messages.success(
            request,
            "The learning session has ended.",
        )
    else:
        messages.info(
            request,
            "There was no active learning session.",
        )

    return redirect("learning:practice")