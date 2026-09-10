from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import unescape

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.html import strip_tags

from courses.models import (
    Enrollment,
    KnowledgeComponent,
    LearningAttempt,
    LearningItem,
    LearningSession,
    StudentKnowledgeState,
)
from ml.features import build_success_prediction_input
from ml.inference import (
    get_bkt_parameters,
    get_bkt_version,
    initial_mastery,
    predict_success_probability,
    update_bkt_mastery,
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


@dataclass(frozen=True)
class RecordedAttempt:
    attempt: LearningAttempt
    knowledge_state: StudentKnowledgeState
    session: LearningSession
    answer_is_correct: bool
    independent_success: bool
    previous_mastery: float
    updated_mastery: float


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

        if not has_usable_answer(item):
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


@transaction.atomic
def get_or_create_active_session(
    enrollment: Enrollment,
    goal_component: KnowledgeComponent | None = None,
) -> LearningSession:
    session = (
        LearningSession.objects
        .select_for_update()
        .filter(
            enrollment=enrollment,
            is_active=True,
            ended_at=None,
        )
        .order_by("-started_at", "-id")
        .first()
    )

    if session is None:
        session = LearningSession.objects.create(
            enrollment=enrollment,
            started_at=timezone.now(),
            is_active=True,
            goal_component=goal_component,
            metadata={
                "source": "database_adaptive_flow",
            },
        )
    elif (
        goal_component is not None
        and session.goal_component_id is None
    ):
        session.goal_component = goal_component
        session.save(
            update_fields=["goal_component"]
        )

    return session


@transaction.atomic
def record_learning_attempt(
    enrollment: Enrollment,
    learning_item: LearningItem,
    submitted_answer: str,
    response_time_ms: int,
    hint_count: int = 0,
    saw_answer: bool = False,
    predicted_success_probability: float | None = None,
) -> RecordedAttempt:
    response_time_ms = max(
        int(response_time_ms),
        0,
    )

    hint_count = max(
        int(hint_count),
        0,
    )

    enrollment = (
        Enrollment.objects
        .select_for_update()
        .select_related("course", "student")
        .get(pk=enrollment.pk)
    )

    learning_item = (
        LearningItem.objects
        .select_related(
            "course",
            "primary_knowledge_component",
        )
        .prefetch_related("knowledge_components")
        .get(pk=learning_item.pk)
    )

    if enrollment.course_id != learning_item.course_id:
        raise ValueError(
            "The enrollment and learning item must "
            "belong to the same course."
        )

    knowledge_component = (
        learning_item.primary_knowledge_component
    )

    if knowledge_component is None:
        raise ValueError(
            "The learning item has no primary "
            "knowledge component."
        )

    session = get_or_create_active_session(
        enrollment=enrollment,
        goal_component=knowledge_component,
    )

    attempt_number = (
        LearningAttempt.objects
        .filter(
            enrollment=enrollment,
            learning_item=learning_item,
        )
        .count()
        + 1
    )

    answer_is_correct = check_learning_item_answer(
        item=learning_item,
        submitted_answer=submitted_answer,
    )

    # Ovo odgovara FoundationalASSIST discrete_score:
    # tačan prvi pokušaj bez hinta i bez prikazanog odgovora.
    independent_success = bool(
        answer_is_correct
        and attempt_number == 1
        and hint_count == 0
        and not saw_answer
    )

    knowledge_state = (
        StudentKnowledgeState.objects
        .select_for_update()
        .filter(
            enrollment=enrollment,
            knowledge_component=knowledge_component,
        )
        .first()
    )

    if (
        knowledge_state is None
        or knowledge_state.mastery_prob is None
    ):
        previous_mastery = float(
            initial_mastery(
                knowledge_component.external_id
            )
        )
    else:
        previous_mastery = float(
            knowledge_state.mastery_prob
        )

    bkt_update = update_bkt_mastery(
        mastery=previous_mastery,
        is_correct=independent_success,
        skill_code=knowledge_component.external_id,
    )

    attempted_at = timezone.now()

    attempt = LearningAttempt.objects.create(
        enrollment=enrollment,
        knowledge_component=knowledge_component,
        learning_item=learning_item,
        session=session,
        external_question_id=(
            learning_item.external_id
        ),
        question_type=learning_item.problem_type,
        student_answer=str(submitted_answer),
        score=1.0 if independent_success else 0.0,
        response_time_ms=response_time_ms,
        hint_count=hint_count,
        saw_answer=bool(saw_answer),
        attempt_number=attempt_number,
        is_correct=independent_success,
        answer_is_correct=answer_is_correct,
        attempted_at=attempted_at,
        context={
            "answer_type": learning_item.answer_type,
            "source_dataset": (
                learning_item.source_dataset
            ),
            "predicted_success_probability": (
                predicted_success_probability
            ),
            "previous_mastery": previous_mastery,
            "updated_mastery": (
                bkt_update.updated_mastery
            ),
            "bkt_source": bkt_update.source,
        },
    )

    if knowledge_state is None:
        knowledge_state = (
            StudentKnowledgeState.objects.create(
                enrollment=enrollment,
                knowledge_component=knowledge_component,
                mastery_prob=(
                    bkt_update.updated_mastery
                ),
                source="trained_bkt",
                source_version=get_bkt_version(),
                evidence_count=1,
                last_attempt_at=attempted_at,
            )
        )
    else:
        knowledge_state.mastery_prob = (
            bkt_update.updated_mastery
        )
        knowledge_state.source = "trained_bkt"
        knowledge_state.source_version = (
            get_bkt_version()
        )
        knowledge_state.evidence_count += 1
        knowledge_state.last_attempt_at = (
            attempted_at
        )
        knowledge_state.save(
            update_fields=[
                "mastery_prob",
                "source",
                "source_version",
                "evidence_count",
                "last_attempt_at",
                "last_updated_at",
            ]
        )

    return RecordedAttempt(
        attempt=attempt,
        knowledge_state=knowledge_state,
        session=session,
        answer_is_correct=answer_is_correct,
        independent_success=independent_success,
        previous_mastery=previous_mastery,
        updated_mastery=(
            bkt_update.updated_mastery
        ),
    )

def check_learning_item_answer(
    item: LearningItem,
    submitted_answer: str,
) -> bool:
    if (
        item.problem_type == "Fill-in-the-blank(s)"
        and item.answer_type == "Numeric"
    ):
        return _check_numeric_answer(
            submitted_answer=submitted_answer,
            accepted_answers=item.fill_in_answers,
        )

    if (
        item.problem_type
        == "Multiple Choice (select 1)"
        and item.answer_type == "Multiple Choice"
    ):
        return _check_multiple_choice_answer(
            submitted_answer=submitted_answer,
            options=item.multiple_choice_options,
            accepted_answers=(
                item.multiple_choice_answers
            ),
        )

    raise ValueError(
        "This learning item type is not currently supported."
    )


def find_correct_choice_index(
    item: LearningItem,
) -> int | None:
    if (
        item.problem_type
        != "Multiple Choice (select 1)"
        or item.answer_type != "Multiple Choice"
    ):
        return None

    normalized_answers = {
        _normalize_text(answer)
        for answer in item.multiple_choice_answers
    }

    for index, option in enumerate(
        item.multiple_choice_options
    ):
        if _normalize_text(option) in normalized_answers:
            return index

    return None


def _check_numeric_answer(
    submitted_answer: str,
    accepted_answers: list,
) -> bool:
    submitted_number = _parse_decimal(
        submitted_answer
    )

    if submitted_number is None:
        return False

    for accepted_answer in accepted_answers:
        accepted_number = _parse_decimal(
            accepted_answer
        )

        if accepted_number is None:
            continue

        tolerance = max(
            Decimal("1e-9"),
            abs(accepted_number) * Decimal("1e-9"),
        )

        if (
            abs(submitted_number - accepted_number)
            <= tolerance
        ):
            return True

    return False


def _check_multiple_choice_answer(
    submitted_answer: str,
    options: list,
    accepted_answers: list,
) -> bool:
    try:
        selected_index = int(submitted_answer)
    except (TypeError, ValueError):
        return False

    if not 0 <= selected_index < len(options):
        return False

    selected_option = _normalize_text(
        options[selected_index]
    )

    accepted_options = {
        _normalize_text(answer)
        for answer in accepted_answers
    }

    return selected_option in accepted_options


def _parse_decimal(value) -> Decimal | None:
    normalized = _normalize_text(value)

    if not normalized:
        return None

    normalized = normalized.replace(",", "")

    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _normalize_text(value) -> str:
    return " ".join(
        unescape(
            strip_tags(str(value))
        ).split()
    ).strip().casefold()


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


def has_usable_answer(item: LearningItem) -> bool:
    if (
        item.problem_type == "Fill-in-the-blank(s)"
        and item.answer_type == "Numeric"
    ):
        return any(
            _parse_decimal(answer) is not None
            for answer in item.fill_in_answers
        )

    if (
        item.problem_type
        == "Multiple Choice (select 1)"
        and item.answer_type == "Multiple Choice"
    ):
        return (
            find_correct_choice_index(item)
            is not None
        )

    return False