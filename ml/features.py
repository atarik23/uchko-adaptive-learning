from datetime import datetime

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from courses.models import Enrollment, LearningItem

from .inference import SuccessPredictionInput


def build_success_prediction_input(
    enrollment: Enrollment,
    learning_item: LearningItem,
    reference_time: datetime | None = None,
) -> SuccessPredictionInput:
    if enrollment.course_id != learning_item.course_id:
        raise ValueError(
            "The enrollment and learning item must belong "
            "to the same course."
        )

    knowledge_component = (
        learning_item.primary_knowledge_component
    )

    if knowledge_component is None:
        raise ValueError(
            "The learning item must have a primary "
            "knowledge component."
        )

    if reference_time is None:
        reference_time = timezone.now()

    attempts = enrollment.learning_attempts.all()

    user_history = attempts.aggregate(
        total=Count("id"),
        correct=Count(
            "id",
            filter=Q(is_correct=True),
        ),
        hints=Coalesce(
            Sum("hint_count"),
            0,
        ),
        saw_answer=Count(
            "id",
            filter=Q(saw_answer=True),
        ),
    )

    skill_attempts = attempts.filter(
        knowledge_component=knowledge_component,
    )

    skill_history = skill_attempts.aggregate(
        total=Count("id"),
        correct=Count(
            "id",
            filter=Q(is_correct=True),
        ),
    )

    previous_attempt = (
        attempts
        .order_by("-attempted_at", "-id")
        .first()
    )

    if previous_attempt is None:
        previous_correct = -1
        previous_used_hint = 0
        hours_since_previous = -1.0
    else:
        previous_correct = int(
            previous_attempt.is_correct
        )

        previous_used_hint = int(
            previous_attempt.hint_count > 0
        )

        elapsed_seconds = (
            reference_time - previous_attempt.attempted_at
        ).total_seconds()

        hours_since_previous = min(
            max(elapsed_seconds / 3600.0, 0.0),
            720.0,
        )

    user_attempt_count = int(
        user_history["total"] or 0
    )

    user_correct_count = int(
        user_history["correct"] or 0
    )

    skill_attempt_count = int(
        skill_history["total"] or 0
    )

    skill_correct_count = int(
        skill_history["correct"] or 0
    )

    # Iste Laplace-smoothed formule korištene su
    # prilikom pripreme trening podataka.
    user_accuracy = (
        user_correct_count + 1.0
    ) / (
        user_attempt_count + 2.0
    )

    skill_accuracy = (
        skill_correct_count + 1.0
    ) / (
        skill_attempt_count + 2.0
    )

    return SuccessPredictionInput(
        problem_id=str(learning_item.external_id),
        problem_set_id=(
            str(learning_item.problem_set_id)
            if learning_item.problem_set_id
            else "unknown"
        ),
        problem_type=(
            str(learning_item.problem_type)
            if learning_item.problem_type
            else "unknown"
        ),
        answer_type=(
            str(learning_item.answer_type)
            if learning_item.answer_type
            else "unknown"
        ),
        primary_skill=str(
            knowledge_component.external_id
        ),
        problem_part=(
            int(learning_item.problem_part)
            if learning_item.problem_part is not None
            else -1
        ),
        skill_count=max(
            int(learning_item.skill_count),
            1,
        ),
        user_attempts_before=user_attempt_count,
        user_correct_before=user_correct_count,
        user_accuracy_before=float(user_accuracy),
        user_hints_before=int(
            user_history["hints"] or 0
        ),
        user_saw_answer_before=int(
            user_history["saw_answer"] or 0
        ),
        previous_correct=previous_correct,
        previous_used_hint=previous_used_hint,
        hours_since_previous=float(
            hours_since_previous
        ),
        skill_attempts_before=skill_attempt_count,
        skill_correct_before=skill_correct_count,
        skill_accuracy_before=float(skill_accuracy),
    )