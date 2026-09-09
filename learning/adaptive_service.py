from dataclasses import dataclass

from django.db.models import Q

from courses.models import (
    Enrollment,
    KnowledgeComponent,
    LearningItem,
    StudentKnowledgeState,
)
from ml.features import build_success_prediction_input
from ml.inference import (
    get_bkt_parameters,
    initial_mastery,
    predict_success_probability,
)


DATASET_NAME = "ASSISTments/FoundationalASSIST"

TARGET_SUCCESS_PROBABILITY = 0.65
WEAKEST_SKILL_LIMIT = 8
ITEMS_PER_SKILL = 5
RECENT_ITEM_LIMIT = 20


@dataclass(frozen=True)
class AdaptiveSelection:
    learning_item: LearningItem
    knowledge_component: KnowledgeComponent
    mastery_probability: float
    success_probability: float
    selection_score: float
    bkt_source: str
    reason: str


def get_student_enrollment(user) -> Enrollment:
    enrollment = (
        Enrollment.objects
        .filter(
            student=user,
            is_active=True,
            course__is_active=True,
            course__learning_items__is_active=True,
            course__learning_items__source_dataset=(
                DATASET_NAME
            ),
        )
        .select_related(
            "course",
            "student",
        )
        .distinct()
        .order_by("enrolled_at", "id")
        .first()
    )

    if enrollment is None:
        raise ValueError(
            "The student is not enrolled in an active "
            "course containing imported learning items."
        )

    return enrollment


def supported_learning_items(enrollment: Enrollment):
    return (
        LearningItem.objects
        .filter(
            course=enrollment.course,
            is_active=True,
            source_dataset=DATASET_NAME,
        )
        .filter(
            Q(
                problem_type="Fill-in-the-blank(s)",
                answer_type="Numeric",
            )
            | Q(
                problem_type="Multiple Choice (select 1)",
                answer_type="Multiple Choice",
            )
        )
        .select_related(
            "primary_knowledge_component",
        )
    )


def get_mastery_probability(
    enrollment: Enrollment,
    knowledge_component: KnowledgeComponent,
    existing_states: dict[int, StudentKnowledgeState] | None = None,
) -> float:
    if existing_states is not None:
        state = existing_states.get(
            knowledge_component.id
        )
    else:
        state = (
            StudentKnowledgeState.objects
            .filter(
                enrollment=enrollment,
                knowledge_component=knowledge_component,
            )
            .first()
        )

    if (
        state is not None
        and state.mastery_prob is not None
    ):
        return float(state.mastery_prob)

    return float(
        initial_mastery(
            knowledge_component.external_id
        )
    )


def select_next_learning_item(
    enrollment: Enrollment,
) -> AdaptiveSelection:
    items = supported_learning_items(enrollment)

    component_ids = list(
        items
        .exclude(
            primary_knowledge_component=None
        )
        .values_list(
            "primary_knowledge_component_id",
            flat=True,
        )
        .distinct()
    )

    if not component_ids:
        raise ValueError(
            "No supported learning items are available "
            "for this course."
        )

    components = list(
        KnowledgeComponent.objects
        .filter(id__in=component_ids)
        .order_by("external_id")
    )

    existing_states = {
        state.knowledge_component_id: state
        for state in (
            StudentKnowledgeState.objects
            .filter(
                enrollment=enrollment,
                knowledge_component_id__in=component_ids,
            )
        )
    }

    mastery_by_component = {
        component.id: get_mastery_probability(
            enrollment=enrollment,
            knowledge_component=component,
            existing_states=existing_states,
        )
        for component in components
    }

    components.sort(
        key=lambda component: (
            mastery_by_component[component.id],
            component.external_id,
        )
    )

    weakest_components = components[
        :WEAKEST_SKILL_LIMIT
    ]

    recent_item_ids = list(
        enrollment.learning_attempts
        .exclude(learning_item=None)
        .order_by("-attempted_at", "-id")
        .values_list(
            "learning_item_id",
            flat=True,
        )[:RECENT_ITEM_LIMIT]
    )

    candidates = _candidate_items(
        items=items,
        components=weakest_components,
        excluded_item_ids=recent_item_ids,
    )

    if not candidates:
        candidates = _candidate_items(
            items=items,
            components=weakest_components,
            excluded_item_ids=[],
        )

    if not candidates:
        raise ValueError(
            "No valid candidate learning items could be selected."
        )

    evaluated_candidates = []

    for item in candidates:
        component = item.primary_knowledge_component

        if component is None:
            continue

        if not _has_usable_answer(item):
            continue

        features = build_success_prediction_input(
            enrollment=enrollment,
            learning_item=item,
        )

        success_probability = (
            predict_success_probability(features)
        )

        mastery_probability = mastery_by_component[
            component.id
        ]

        # Najprije tražimo zadatak s procijenjenom
        # vjerovatnoćom uspjeha blizu 65%.
        # Mali mastery dodatak daje prednost slabijim
        # vještinama kada su zadaci inače slični.
        selection_score = (
            abs(
                success_probability
                - TARGET_SUCCESS_PROBABILITY
            )
            + 0.10 * mastery_probability
        )

        parameters = get_bkt_parameters(
            component.external_id
        )

        evaluated_candidates.append(
            AdaptiveSelection(
                learning_item=item,
                knowledge_component=component,
                mastery_probability=(
                    mastery_probability
                ),
                success_probability=(
                    success_probability
                ),
                selection_score=selection_score,
                bkt_source=parameters.source,
                reason=(
                    "Selected from the student's weakest "
                    "skills with predicted success closest "
                    "to the 65% learning target."
                ),
            )
        )

    if not evaluated_candidates:
        raise ValueError(
            "Candidate items exist, but none contains "
            "a usable supported answer."
        )

    return min(
        evaluated_candidates,
        key=lambda selection: (
            selection.selection_score,
            selection.learning_item.id,
        ),
    )


def _candidate_items(
    items,
    components: list[KnowledgeComponent],
    excluded_item_ids: list[int],
) -> list[LearningItem]:
    candidates = []

    for component in components:
        component_items = (
            items
            .filter(
                primary_knowledge_component=component,
            )
            .exclude(id__in=excluded_item_ids)
            .order_by("?")[:ITEMS_PER_SKILL]
        )

        candidates.extend(component_items)

    return candidates


def _has_usable_answer(item: LearningItem) -> bool:
    if (
        item.problem_type == "Fill-in-the-blank(s)"
        and item.answer_type == "Numeric"
    ):
        return bool(item.fill_in_answers)

    if (
        item.problem_type
        == "Multiple Choice (select 1)"
        and item.answer_type == "Multiple Choice"
    ):
        return bool(
            item.multiple_choice_options
            and item.multiple_choice_answers
        )

    return False