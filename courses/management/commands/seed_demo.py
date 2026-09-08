from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from courses.models import (
    Course,
    Enrollment,
    KnowledgeComponent,
    LearningAttempt,
    LearningSession,
    StudentKnowledgeState,
)


DEMO_PASSWORD = "UchkoDemo2026!"


class Command(BaseCommand):
    help = "Create idempotent demo data for Uchko."

    @transaction.atomic
    def handle(self, *args, **options):
        professor = self.create_user(
            username="professor_demo",
            email="professor.demo@uchko.local",
            first_name="Demo",
            last_name="Professor",
            role=User.Role.PROFESSOR,
        )

        student_one = self.create_user(
            username="student_demo_1",
            email="student1.demo@uchko.local",
            first_name="Amina",
            last_name="Hodžić",
            role=User.Role.STUDENT,
        )

        student_two = self.create_user(
            username="student_demo_2",
            email="student2.demo@uchko.local",
            first_name="Emir",
            last_name="Kovačević",
            role=User.Role.STUDENT,
        )

        course, _ = Course.objects.update_or_create(
            code="UCHKO-DEMO",
            defaults={
                "name": "Adaptive Learning Demo",
                "professor": professor,
                "description": (
                    "Dataset-independent demonstration course for "
                    "adaptive learning."
                ),
                "is_active": True,
            },
        )

        enrollment_one, _ = Enrollment.objects.update_or_create(
            course=course,
            student=student_one,
            defaults={"is_active": True},
        )

        enrollment_two, _ = Enrollment.objects.update_or_create(
            course=course,
            student=student_two,
            defaults={"is_active": True},
        )

        foundation, _ = KnowledgeComponent.objects.update_or_create(
            course=course,
            external_id="KC_FOUNDATION",
            defaults={
                "name": "Foundational Knowledge",
                "description": "Basic concepts required by later components.",
                "parent": None,
                "metadata": {"demo": True, "level": 1},
            },
        )

        concepts, _ = KnowledgeComponent.objects.update_or_create(
            course=course,
            external_id="KC_CONCEPTS",
            defaults={
                "name": "Conceptual Understanding",
                "description": "Understanding and connecting core concepts.",
                "parent": foundation,
                "metadata": {"demo": True, "level": 2},
            },
        )

        application, _ = KnowledgeComponent.objects.update_or_create(
            course=course,
            external_id="KC_APPLICATION",
            defaults={
                "name": "Problem Application",
                "description": "Applying acquired knowledge to problems.",
                "parent": concepts,
                "metadata": {"demo": True, "level": 3},
            },
        )

        now = timezone.now()

        self.create_student_data(
            enrollment=enrollment_one,
            components=[foundation, concepts, application],
            mastery_values=[0.90, 0.72, 0.48],
            correctness_values=[True, True, True, False, True, False],
            now=now,
            seed_prefix="student-one",
        )

        self.create_student_data(
            enrollment=enrollment_two,
            components=[foundation, concepts, application],
            mastery_values=[0.76, 0.51, 0.28],
            correctness_values=[True, False, True, False, False, False],
            now=now - timedelta(hours=3),
            seed_prefix="student-two",
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data created or updated successfully."
            )
        )

        self.stdout.write("")
        self.stdout.write("Professor:")
        self.stdout.write("  username: professor_demo")
        self.stdout.write(f"  password: {DEMO_PASSWORD}")

        self.stdout.write("")
        self.stdout.write("Students:")
        self.stdout.write("  student_demo_1")
        self.stdout.write("  student_demo_2")
        self.stdout.write(f"  password: {DEMO_PASSWORD}")

    def create_user(
        self,
        username,
        email,
        first_name,
        last_name,
        role,
    ):
        user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "role": role,
                "is_active": True,
            },
        )

        user.set_password(DEMO_PASSWORD)
        user.save()

        return user

    def create_student_data(
        self,
        enrollment,
        components,
        mastery_values,
        correctness_values,
        now,
        seed_prefix,
    ):
        session = (
            LearningSession.objects
            .filter(
                enrollment=enrollment,
                metadata__seed_id=f"{seed_prefix}-session",
            )
            .first()
        )

        session_start = now - timedelta(minutes=24)
        session_end = now

        if session is None:
            session = LearningSession.objects.create(
                enrollment=enrollment,
                started_at=session_start,
                ended_at=session_end,
                is_active=False,
                goal_component=components[-1],
                metadata={
                    "demo": True,
                    "seed_id": f"{seed_prefix}-session",
                },
            )
        else:
            session.started_at = session_start
            session.ended_at = session_end
            session.is_active = False
            session.goal_component = components[-1]
            session.metadata = {
                "demo": True,
                "seed_id": f"{seed_prefix}-session",
            }
            session.save()

        latest_attempt_by_component = {}

        for index, is_correct in enumerate(correctness_values, start=1):
            component = components[(index - 1) % len(components)]
            attempted_at = session_start + timedelta(minutes=index * 3)
            question_id = f"{seed_prefix}-question-{index}"

            attempt, _ = LearningAttempt.objects.update_or_create(
                enrollment=enrollment,
                external_question_id=question_id,
                attempt_number=1,
                defaults={
                    "knowledge_component": component,
                    "session": session,
                    "question_type": "demo",
                    "student_answer": (
                        "demo-correct-answer"
                        if is_correct
                        else "demo-incorrect-answer"
                    ),
                    "score": 1.0 if is_correct else 0.0,
                    "response_time_ms": 18000 + index * 2400,
                    "hint_count": 0 if is_correct else 1,
                    "is_correct": is_correct,
                    "attempted_at": attempted_at,
                    "context": {
                        "demo": True,
                        "seed_id": question_id,
                    },
                },
            )

            latest_attempt_by_component[component.id] = attempt.attempted_at

        for component, mastery in zip(components, mastery_values):
            StudentKnowledgeState.objects.update_or_create(
                enrollment=enrollment,
                knowledge_component=component,
                defaults={
                    "mastery_prob": mastery,
                    "source": "demo_seed",
                    "source_version": "1.0",
                    "evidence_count": 2,
                    "last_attempt_at": latest_attempt_by_component.get(
                        component.id
                    ),
                },
            )