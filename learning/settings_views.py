from __future__ import annotations

from django.db.models import Max
from django.shortcuts import render

from accounts.decorators import student_required
from courses.models import (
    LearningAttempt,
    LearningSession,
    StudentKnowledgeState,
)

from .adaptive_service import (
    DATASET_NAME,
    get_student_enrollment,
)


@student_required
def settings_view(request):
    user = request.user

    try:
        enrollment = get_student_enrollment(
            user
        )
    except ValueError:
        enrollment = None

    total_attempts = 0
    total_sessions = 0
    tracked_skills = 0
    last_activity = None
    active_session = None

    if enrollment is not None:
        attempts = LearningAttempt.objects.filter(
            enrollment=enrollment,
        )

        total_attempts = attempts.count()

        last_activity = attempts.aggregate(
            last_activity=Max("attempted_at")
        )["last_activity"]

        sessions = LearningSession.objects.filter(
            enrollment=enrollment,
        )

        total_sessions = sessions.count()

        active_session = (
            sessions
            .filter(
                is_active=True,
                ended_at=None,
            )
            .order_by(
                "-started_at",
                "-id",
            )
            .first()
        )

        tracked_skills = (
            StudentKnowledgeState.objects
            .filter(
                enrollment=enrollment,
                evidence_count__gt=0,
            )
            .count()
        )

    context = {
        "active_tab": "settings",
        "account_user": user,
        "enrollment": enrollment,
        "course": (
            enrollment.course
            if enrollment is not None
            else None
        ),
        "total_attempts": total_attempts,
        "total_sessions": total_sessions,
        "tracked_skills": tracked_skills,
        "last_activity": last_activity,
        "active_session": active_session,
        "dataset_name": DATASET_NAME,
    }

    return render(
        request,
        "learning/settings.html",
        context,
    )