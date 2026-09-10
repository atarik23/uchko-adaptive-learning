from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import render

from accounts.decorators import student_required
from courses.models import (
    KnowledgeComponent,
    LearningAttempt,
    StudentKnowledgeState,
)
from ml.inference import initial_mastery

from .adaptive_service import (
    DATASET_NAME,
    get_student_enrollment,
)


@student_required
def curriculum_view(request):
    try:
        enrollment = get_student_enrollment(
            request.user
        )
    except ValueError as error:
        return render(
            request,
            "learning/curriculum.html",
            {
                "active_tab": "curriculum",
                "setup_error": str(error),
            },
        )

    components = list(
        KnowledgeComponent.objects
        .filter(
            course=enrollment.course,
            primary_learning_items__source_dataset=(
                DATASET_NAME
            ),
            primary_learning_items__is_active=True,
        )
        .annotate(
            total_item_count=Count(
                "primary_learning_items",
                filter=Q(
                    primary_learning_items__source_dataset=(
                        DATASET_NAME
                    ),
                    primary_learning_items__is_active=True,
                ),
                distinct=True,
            ),
            supported_item_count=Count(
                "primary_learning_items",
                filter=(
                    Q(
                        primary_learning_items__source_dataset=(
                            DATASET_NAME
                        ),
                        primary_learning_items__is_active=True,
                        primary_learning_items__problem_type=(
                            "Fill-in-the-blank(s)"
                        ),
                        primary_learning_items__answer_type=(
                            "Numeric"
                        ),
                    )
                    | Q(
                        primary_learning_items__source_dataset=(
                            DATASET_NAME
                        ),
                        primary_learning_items__is_active=True,
                        primary_learning_items__problem_type=(
                            "Multiple Choice (select 1)"
                        ),
                        primary_learning_items__answer_type=(
                            "Multiple Choice"
                        ),
                    )
                ),
                distinct=True,
            ),
        )
        .distinct()
        .order_by("external_id")
    )

    existing_states = {
        state.knowledge_component_id: state
        for state in (
            StudentKnowledgeState.objects
            .filter(
                enrollment=enrollment,
                knowledge_component__in=components,
            )
        )
    }

    attempt_counts = {
        row["knowledge_component_id"]: row[
            "attempt_count"
        ]
        for row in (
            LearningAttempt.objects
            .filter(
                enrollment=enrollment,
                knowledge_component__in=components,
            )
            .values("knowledge_component_id")
            .annotate(
                attempt_count=Count("id")
            )
        )
    }

    curriculum_rows = []

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
            evidence_count = (
                state.evidence_count
            )
            mastery_source = state.source
        else:
            mastery = float(
                initial_mastery(
                    component.external_id
                )
            )
            evidence_count = 0
            mastery_source = "initial_bkt"

        curriculum_rows.append(
            {
                "id": component.id,
                "skill_id": (
                    component.external_id
                ),
                "skill_name": component.name,
                "description": (
                    component.description
                ),
                "mastery": mastery,
                "mastery_percentage": (
                    mastery * 100.0
                ),
                "mastery_source": (
                    mastery_source
                ),
                "evidence_count": (
                    evidence_count
                ),
                "attempt_count": (
                    attempt_counts.get(
                        component.id,
                        0,
                    )
                ),
                "total_item_count": (
                    component.total_item_count
                ),
                "supported_item_count": (
                    component.supported_item_count
                ),
            }
        )

    selected_skill_id = (
        request.GET.get("skill") or ""
    ).strip()

    selected_row = None

    if selected_skill_id:
        selected_row = next(
            (
                row
                for row in curriculum_rows
                if row["skill_id"]
                == selected_skill_id
            ),
            None,
        )

    if (
        selected_row is None
        and curriculum_rows
    ):
        selected_row = curriculum_rows[0]

    total_item_count = sum(
        row["total_item_count"]
        for row in curriculum_rows
    )

    supported_item_count = sum(
        row["supported_item_count"]
        for row in curriculum_rows
    )

    context = {
        "active_tab": "curriculum",
        "enrollment": enrollment,
        "course": enrollment.course,
        "curriculum_rows": curriculum_rows,
        "selected_row": selected_row,
        "skill_count": len(
            curriculum_rows
        ),
        "total_item_count": (
            total_item_count
        ),
        "supported_item_count": (
            supported_item_count
        ),
    }

    return render(
        request,
        "learning/curriculum.html",
        context,
    )