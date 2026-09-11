import random
from dataclasses import dataclass
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from courses.models import (
    Course,
    Enrollment,
    LearningAttempt,
    LearningItem,
    LearningSession,
    StudentKnowledgeState,
)


DEMO_PASSWORD = "UchkoDemo2026!"
COURSE_CODE = "UCHKO-DEMO"
SEED_VERSION = "synthetic-demo-v2"


@dataclass(frozen=True)
class StudentSpec:
    username: str
    first_name: str
    last_name: str
    ability: float
    sessions: int


STUDENTS = [
    StudentSpec("student_01", "Amina", "Hodzic", 0.82, 5),
    StudentSpec("student_02", "Emir", "Kovacevic", 0.48, 3),
    StudentSpec("student_03", "Lejla", "Basic", 0.74, 4),
    StudentSpec("student_04", "Haris", "Music", 0.57, 4),
    StudentSpec("student_05", "Sara", "Delic", 0.88, 5),
    StudentSpec("student_06", "Adnan", "Selimovic", 0.43, 2),
    StudentSpec("student_07", "Ena", "Mujkic", 0.68, 4),
    StudentSpec("student_08", "Kerim", "Softic", 0.61, 3),
    StudentSpec("student_09", "Mia", "Kadic", 0.77, 5),
    StudentSpec("student_10", "Amar", "Kurtovic", 0.35, 2),
    StudentSpec("student_11", "Hana", "Imamovic", 0.71, 4),
    StudentSpec("student_12", "Tarik", "Mesic", 0.54, 3),
    StudentSpec("student_13", "Ajla", "Hadzic", 0.91, 5),
    StudentSpec("student_14", "Nedim", "Becirovic", 0.64, 3),
    StudentSpec("student_15", "Lamija", "Cengic", 0.46, 2),
]


class Command(BaseCommand):
    help = "Create deterministic synthetic demonstration data for Uchko."

    @transaction.atomic
    def handle(self, *args, **options):
        professor = self._create_or_update_professor()
        course = self._get_course(professor)
        items = list(
            LearningItem.objects.filter(
                course=course,
                is_active=True,
                primary_knowledge_component__isnull=False,
            )
            .select_related("primary_knowledge_component")
            .order_by("id")
        )
        if not items:
            raise CommandError(
                "No active learning items with a primary knowledge component "
                "were found. Import FoundationalASSIST before seeding demo data."
            )

        self._migrate_legacy_students()
        generated_attempts = 0
        for index, spec in enumerate(STUDENTS, start=1):
            student = self._create_or_update_student(spec)
            enrollment, _ = Enrollment.objects.update_or_create(
                course=course,
                student=student,
                defaults={"is_active": True},
            )
            self._remove_previous_synthetic_activity(enrollment)
            generated_attempts += self._create_student_activity(
                enrollment=enrollment,
                spec=spec,
                items=items,
                student_index=index,
            )

        self._deactivate_unused_legacy_professor()
        self.stdout.write(
            self.style.SUCCESS(
                f"Synthetic demo data ready: {len(STUDENTS)} students, "
                f"{generated_attempts} attempts."
            )
        )
        self.stdout.write("")
        self.stdout.write("Professor:")
        self.stdout.write("  username: instructor")
        self.stdout.write(f"  password: {DEMO_PASSWORD}")
        self.stdout.write("")
        self.stdout.write("Students: student_01 through student_15")
        self.stdout.write(f"Password: {DEMO_PASSWORD}")
        self.stdout.write("All generated activity is synthetic demonstration data.")

    def _create_or_update_professor(self):
        professor = User.objects.filter(username="instructor").first()
        legacy = User.objects.filter(username="professor_demo").first()
        if professor is None and legacy is not None:
            legacy.username = "instructor"
            professor = legacy
        if professor is None:
            professor = User(username="instructor")

        professor.email = "instructor@uchko.local"
        professor.first_name = "Professor"
        professor.last_name = ""
        professor.role = User.Role.PROFESSOR
        professor.is_active = True
        professor.set_password(DEMO_PASSWORD)
        professor.save()
        return professor

    def _get_course(self, professor):
        course, _ = Course.objects.update_or_create(
            code=COURSE_CODE,
            defaults={
                "name": "Adaptive Learning",
                "professor": professor,
                "description": (
                    "Adaptive mathematics practice using knowledge tracing "
                    "and success prediction."
                ),
                "is_active": True,
            },
        )
        return course

    def _migrate_legacy_students(self):
        for old_username, new_username in (
            ("student_demo_1", "student_01"),
            ("student_demo_2", "student_02"),
        ):
            old_user = User.objects.filter(username=old_username).first()
            new_user = User.objects.filter(username=new_username).first()
            if old_user is not None and new_user is None:
                old_user.username = new_username
                old_user.save(update_fields=["username"])

    def _create_or_update_student(self, spec):
        student, _ = User.objects.update_or_create(
            username=spec.username,
            defaults={
                "email": f"{spec.username}@uchko.local",
                "first_name": spec.first_name,
                "last_name": spec.last_name,
                "role": User.Role.STUDENT,
                "is_active": True,
            },
        )
        student.set_password(DEMO_PASSWORD)
        student.save(update_fields=["password"])
        return student

    def _remove_previous_synthetic_activity(self, enrollment):
        LearningAttempt.objects.filter(
            enrollment=enrollment,
            context__seed_version=SEED_VERSION,
        ).delete()
        LearningAttempt.objects.filter(
            enrollment=enrollment,
            context__demo=True,
        ).delete()
        LearningSession.objects.filter(
            enrollment=enrollment,
            metadata__seed_version=SEED_VERSION,
        ).delete()
        LearningSession.objects.filter(
            enrollment=enrollment,
            metadata__demo=True,
        ).delete()
        StudentKnowledgeState.objects.filter(
            enrollment=enrollment,
            source__in=["demo_seed", "synthetic_demo_seed"],
        ).delete()

    def _create_student_activity(self, enrollment, spec, items, student_index):
        rng = random.Random(20260911 + student_index)
        now = timezone.now()
        evidence = {}
        attempts_created = 0

        for session_index in range(spec.sessions):
            days_ago = (spec.sessions - session_index - 1) * 4 + student_index % 3
            start = now - timedelta(
                days=days_ago,
                hours=9 + student_index % 6,
                minutes=session_index * 7,
            )
            attempts_in_session = 5 + rng.randint(0, 3)
            duration_minutes = attempts_in_session * 3 + rng.randint(4, 10)
            end = start + timedelta(minutes=duration_minutes)
            goal_item = items[(student_index * 37 + session_index * 19) % len(items)]
            session = LearningSession.objects.create(
                enrollment=enrollment,
                started_at=start,
                ended_at=end,
                is_active=False,
                goal_component=goal_item.primary_knowledge_component,
                metadata={
                    "synthetic": True,
                    "seed_version": SEED_VERSION,
                    "session_index": session_index + 1,
                },
            )

            for position in range(attempts_in_session):
                item_index = (
                    student_index * 101
                    + session_index * 43
                    + position * 17
                    + rng.randrange(len(items))
                ) % len(items)
                item = items[item_index]
                component = item.primary_knowledge_component
                literal_correct = rng.random() < spec.ability
                help_probability = max(0.05, 0.42 - spec.ability * 0.32)
                used_help = rng.random() < help_probability
                saw_answer = used_help and rng.random() < 0.22
                hint_count = rng.randint(1, 2) if used_help else 0
                independent_success = literal_correct and not used_help and not saw_answer
                attempted_at = start + timedelta(
                    minutes=2 + position * 3,
                    seconds=rng.randint(5, 50),
                )
                response_time_ms = rng.randint(14_000, 82_000)

                LearningAttempt.objects.create(
                    enrollment=enrollment,
                    knowledge_component=component,
                    learning_item=item,
                    session=session,
                    external_question_id=item.external_id,
                    question_type=item.problem_type or item.answer_type or "practice",
                    student_answer=(
                        "synthetic-correct-response"
                        if literal_correct
                        else "synthetic-incorrect-response"
                    ),
                    score=1.0 if literal_correct else 0.0,
                    response_time_ms=response_time_ms,
                    hint_count=hint_count,
                    saw_answer=saw_answer,
                    attempt_number=1,
                    is_correct=independent_success,
                    answer_is_correct=literal_correct,
                    attempted_at=attempted_at,
                    context={
                        "synthetic": True,
                        "seed_version": SEED_VERSION,
                        "session_index": session_index + 1,
                        "position": position + 1,
                    },
                )
                attempts_created += 1
                values = evidence.setdefault(component.id, [component, 0, 0, None])
                values[1] += 1
                values[2] += int(independent_success)
                values[3] = attempted_at

        for component, count, successes, last_attempt in evidence.values():
            observed_rate = (successes + 1.0) / (count + 2.0)
            mastery = min(0.95, max(0.05, 0.10 + 0.82 * observed_rate))
            StudentKnowledgeState.objects.update_or_create(
                enrollment=enrollment,
                knowledge_component=component,
                defaults={
                    "mastery_prob": round(mastery, 6),
                    "source": "synthetic_demo_seed",
                    "source_version": "2.0",
                    "evidence_count": count,
                    "last_attempt_at": last_attempt,
                },
            )

        return attempts_created

    def _deactivate_unused_legacy_professor(self):
        legacy = User.objects.filter(username="prof_demo").first()
        if legacy is not None and not legacy.courses_taught.exists():
            legacy.is_active = False
            legacy.save(update_fields=["is_active"])
