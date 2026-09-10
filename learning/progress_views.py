from __future__ import annotations

from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import render

from accounts.decorators import student_required
from courses.models import (
    KnowledgeComponent,
    LearningAttempt,
    LearningSession,
    StudentKnowledgeState,
)
from ml.inference import initial_mastery

from .adaptive_service import (
    DATASET_NAME,
    get_student_enrollment,
)


MASTERY_THRESHOLD = 0.80


@student_required
def progress_view(request):
    try:
        enrollment = get_student_enrollment(
            request.user
        )
    except ValueError as error:
        return render(
            request,
            "learning/progress.html",
            {
                "active_tab": "progress",
                "setup_error": str(error),
            },
        )

    attempts = LearningAttempt.objects.filter(
        enrollment=enrollment,
    )

    attempt_summary = attempts.aggregate(
        total_attempts=Count("id"),
        correct_answers=Count(
            "id",
            filter=Q(answer_is_correct=True),
        ),
        independent_successes=Count(
            "id",
            filter=Q(is_correct=True),
        ),
        average_response_time_ms=Avg(
            "response_time_ms"
        ),
        total_hints=Sum("hint_count"),
    )

    total_attempts = (
        attempt_summary["total_attempts"] or 0
    )
    correct_answers = (
        attempt_summary["correct_answers"] or 0
    )
    independent_successes = (
        attempt_summary["independent_successes"]
        or 0
    )
    total_hints = (
        attempt_summary["total_hints"] or 0
    )

    if total_attempts:
        answer_accuracy = (
            correct_answers / total_attempts
        )
        independent_success_rate = (
            independent_successes
            / total_attempts
        )
    else:
        answer_accuracy = 0.0
        independent_success_rate = 0.0

    average_response_time_ms = (
        attempt_summary[
            "average_response_time_ms"
        ]
    )

    average_response_time_seconds = (
        average_response_time_ms / 1000.0
        if average_response_time_ms is not None
        else None
    )

    components = (
        KnowledgeComponent.objects
        .filter(
            course=enrollment.course,
            primary_learning_items__source_dataset=(
                DATASET_NAME
            ),
            primary_learning_items__is_active=True,
        )
        .distinct()
        .order_by(
            "external_id"
        )
    )

    existing_states = {
        state.knowledge_component_id: state
        for state in (
            StudentKnowledgeState.objects
            .filter(
                enrollment=enrollment,
                knowledge_component__in=components,
            )
            .select_related(
                "knowledge_component"
            )
        )
    }

    mastery_rows = []

    for component in components:
        state = existing_states.get(
            component.id
        )

        if (
            state is not None
            and state.mastery_prob is not None
        ):
            mastery = float(
                state.mastery_prob
            )
            source = state.source
            evidence_count = (
                state.evidence_count
            )
            last_attempt_at = (
                state.last_attempt_at
            )
        else:
            mastery = float(
                initial_mastery(
                    component.external_id
                )
            )
            source = "initial_bkt"
            evidence_count = 0
            last_attempt_at = None

        mastery_rows.append(
            {
                "skill_id": (
                    component.external_id
                ),
                "skill_name": component.name,
                "mastery": mastery,
                "mastery_percentage": (
                    mastery * 100.0
                ),
                "source": source,
                "evidence_count": (
                    evidence_count
                ),
                "last_attempt_at": (
                    last_attempt_at
                ),
                "is_mastered": (
                    mastery >= MASTERY_THRESHOLD
                ),
            }
        )

    mastery_rows.sort(
        key=lambda row: (
            row["mastery"],
            row["skill_id"],
        )
    )

    skill_count = len(mastery_rows)

    mastered_skill_count = sum(
        row["is_mastered"]
        for row in mastery_rows
    )

    practiced_skill_count = sum(
        row["evidence_count"] > 0
        for row in mastery_rows
    )

    average_mastery = (
        sum(
            row["mastery"]
            for row in mastery_rows
        )
        / skill_count
        if skill_count
        else 0.0
    )

    sessions = LearningSession.objects.filter(
        enrollment=enrollment,
    )

    session_summary = sessions.aggregate(
        total_sessions=Count("id"),
        active_sessions=Count(
            "id",
            filter=Q(
                is_active=True,
                ended_at=None,
            ),
        ),
    )

    recent_attempts = (
        attempts
        .select_related(
            "learning_item",
            "knowledge_component",
        )
        .order_by(
            "-attempted_at",
            "-id",
        )[:10]
    )

    context = {
        "active_tab": "progress",
        "enrollment": enrollment,
        "course": enrollment.course,
        "total_attempts": total_attempts,
        "correct_answers": correct_answers,
        "independent_successes": (
            independent_successes
        ),
        "answer_accuracy": answer_accuracy,
        "independent_success_rate": (
            independent_success_rate
        ),
        "average_response_time_seconds": (
            average_response_time_seconds
        ),
        "total_hints": total_hints,
        "skill_count": skill_count,
        "mastered_skill_count": (
            mastered_skill_count
        ),
        "practiced_skill_count": (
            practiced_skill_count
        ),
        "average_mastery": average_mastery,
        "mastery_rows": mastery_rows,
        "total_sessions": (
            session_summary["total_sessions"]
            or 0
        ),
        "active_sessions": (
            session_summary["active_sessions"]
            or 0
        ),
        "recent_attempts": recent_attempts,
        "mastery_threshold": (
            MASTERY_THRESHOLD
        ),
    }

    return render(
        request,
        "learning/progress.html",
        context,
    )