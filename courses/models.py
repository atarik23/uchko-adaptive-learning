import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from accounts.models import User


def generate_enrollment_code():
    return secrets.token_urlsafe(12)


class Course(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30, unique=True)

    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="courses_taught",
        limit_choices_to={"role": User.Role.PROFESSOR},
    )

    description = models.TextField(blank=True)

    enrollment_code = models.CharField(
        max_length=64,
        unique=True,
        default=generate_enrollment_code,
        editable=False,
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()

        if self.professor_id and self.professor.role != User.Role.PROFESSOR:
            raise ValidationError(
                {
                    "professor": (
                        "The course professor must have the professor role."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} — {self.name}"


class Enrollment(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
        limit_choices_to={"role": User.Role.STUDENT},
    )

    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "student"],
                name="unique_course_student",
            )
        ]

    def clean(self):
        super().clean()

        if self.student_id and self.student.role != User.Role.STUDENT:
            raise ValidationError(
                {
                    "student": (
                        "Only users with the student role can be enrolled "
                        "in a course."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.username} enrolled in {self.course.code}"

class KnowledgeComponent(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="knowledge_components",
    )

    external_id = models.CharField(
        max_length=200,
    )

    name = models.CharField(
        max_length=300,
    )

    description = models.TextField(
        blank=True,
    )

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "external_id"],
                name="unique_component_per_course",
            )
        ]

    def clean(self):
        super().clean()

        if self.parent_id and self.parent.course_id != self.course_id:
            raise ValidationError(
                {
                    "parent": (
                        "A knowledge component parent must belong to the same course."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.external_id} — {self.name}"

class StudentKnowledgeState(models.Model):
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="knowledge_states",
    )

    knowledge_component = models.ForeignKey(
        KnowledgeComponent,
        on_delete=models.CASCADE,
        related_name="student_states",
    )

    mastery_prob = models.FloatField(
        null=True,
        blank=True,
        default=None,
        validators=[
            MinValueValidator(0.0),
            MaxValueValidator(1.0),
        ],
    )

    source = models.CharField(
        max_length=100,
        default="unknown",
    )

    source_version = models.CharField(
        max_length=100,
        blank=True,
    )

    evidence_count = models.PositiveIntegerField(
        default=0,
    )

    last_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "knowledge_component"],
                name="unique_student_state_per_component",
            )
        ]

    def clean(self):
        super().clean()

        if self.enrollment_id and self.knowledge_component_id:
            if self.enrollment.course_id != self.knowledge_component.course_id:
                raise ValidationError(
                    {
                        "knowledge_component": (
                            "The knowledge component must belong to the same course as the enrollment."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.enrollment.student.username} — "
            f"{self.knowledge_component.external_id} "
            f"({self.knowledge_component.course.code})"
        )

class LearningAttempt(models.Model):
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="learning_attempts",
    )

    knowledge_component = models.ForeignKey(
        KnowledgeComponent,
        on_delete=models.CASCADE,
        related_name="learning_attempts",
    )

    learning_item = models.ForeignKey(
        "LearningItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="learning_attempts",
    )

    session = models.ForeignKey(
        "LearningSession",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="learning_attempts",
    )

    external_question_id = models.CharField(
        max_length=200,
        blank=True,
    )

    question_type = models.CharField(
        max_length=50,
        blank=True,
    )

    student_answer = models.TextField(
        blank=True,
    )

    score = models.FloatField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(0.0),
            MaxValueValidator(1.0),
        ],
    )

    response_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    hint_count = models.PositiveIntegerField(
        default=0,
    )

    saw_answer = models.BooleanField(
        default=False,
    )

    attempt_number = models.PositiveIntegerField(
        default=1,
    )

    is_correct = models.BooleanField()

    answer_is_correct = models.BooleanField(
        default=False,
    )

    attempted_at = models.DateTimeField()

    context = models.JSONField(
        default=dict,
        blank=True,
    )

    def clean(self):
        super().clean()

        if self.enrollment_id and self.knowledge_component_id:
            if (
                self.enrollment.course_id
                != self.knowledge_component.course_id
            ):
                raise ValidationError(
                    {
                        "knowledge_component": (
                            "The knowledge component must belong to the "
                            "same course as the enrollment."
                        )
                    }
                )

        if self.learning_item_id and self.enrollment_id:
            if (
                self.learning_item.course_id
                != self.enrollment.course_id
            ):
                raise ValidationError(
                    {
                        "learning_item": (
                            "The learning item must belong to the same "
                            "course as the enrollment."
                        )
                    }
                )

        if self.learning_item_id and self.knowledge_component_id:
            item_component_ids = set(
                self.learning_item
                .knowledge_components
                .values_list("id", flat=True)
            )

            primary_component_id = (
                self.learning_item.primary_knowledge_component_id
            )

            if (
                self.knowledge_component_id
                != primary_component_id
                and self.knowledge_component_id
                not in item_component_ids
            ):
                raise ValidationError(
                    {
                        "knowledge_component": (
                            "The attempt knowledge component must be "
                            "associated with the selected learning item."
                        )
                    }
                )

        if self.session_id and self.enrollment_id:
            if self.session.enrollment_id != self.enrollment_id:
                raise ValidationError(
                    {
                        "session": (
                            "The learning attempt and session must belong "
                            "to the same enrollment."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        if self.learning_item_id and not self.external_question_id:
            self.external_question_id = (
                self.learning_item.external_id
            )

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        correctness = "correct" if self.is_correct else "incorrect"
        return (
            f"{self.enrollment.student.username} — "
            f"{self.knowledge_component.external_id} "
            f"({self.knowledge_component.course.code}) — {correctness}"
        )

class LearningSession(models.Model):
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="learning_sessions",
    )

    started_at = models.DateTimeField()

    ended_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    goal_component = models.ForeignKey(
        KnowledgeComponent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="goal_sessions",
    )

    duration_seconds = models.IntegerField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    def clean(self):
        super().clean()

        # Sesija ne može završiti prije nego što je počela.
        if self.started_at and self.ended_at:
            if self.ended_at < self.started_at:
                raise ValidationError(
                    {
                        "ended_at": (
                            "The session cannot end before it starts."
                        )
                    }
                )

        # Završena sesija više ne može biti označena kao aktivna.
        if self.ended_at and self.is_active:
            raise ValidationError(
                {
                    "is_active": (
                        "A completed session cannot remain active."
                    )
                }
            )

        # Ciljna komponenta mora pripadati istom kursu.
        if (
            self.goal_component_id
            and self.enrollment_id
            and self.goal_component.course_id != self.enrollment.course_id
        ):
            raise ValidationError(
                {
                    "goal_component": (
                        "The goal component must belong to the same "
                        "course as the session."
                    )
                }
            )

        # Svi povezani pokušaji moraju pripadati istom enrollmentu.
        if self.pk and self.enrollment_id:
            for attempt in self.learning_attempts.all():
                if attempt.enrollment_id != self.enrollment_id:
                    raise ValidationError(
                        "All attempts in a session must belong to the "
                        "same enrollment as the session."
                    )

    def save(self, *args, **kwargs):
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())
        else:
            self.duration_seconds = None

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        duration = (
            f"{self.duration_seconds}s"
            if self.duration_seconds is not None
            else "ongoing"
        )

        return (
            f"{self.enrollment.student.username} — "
            f"{self.enrollment.course.code} — "
            f"{duration} — {self.started_at}"
        )


class LearningItem(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="learning_items",
    )

    external_id = models.CharField(
        max_length=200,
    )

    problem_set_id = models.CharField(
        max_length=200,
        blank=True,
    )

    problem_part = models.IntegerField(
        null=True,
        blank=True,
    )

    problem_type = models.CharField(
        max_length=100,
        blank=True,
    )

    answer_type = models.CharField(
        max_length=100,
        blank=True,
    )

    body = models.TextField()

    fill_in_options = models.JSONField(
        default=list,
        blank=True,
    )

    fill_in_answers = models.JSONField(
        default=list,
        blank=True,
    )

    multiple_choice_options = models.JSONField(
        default=list,
        blank=True,
    )

    multiple_choice_answers = models.JSONField(
        default=list,
        blank=True,
    )

    primary_knowledge_component = models.ForeignKey(
        KnowledgeComponent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="primary_learning_items",
    )

    knowledge_components = models.ManyToManyField(
        KnowledgeComponent,
        blank=True,
        related_name="learning_items",
    )

    skill_count = models.PositiveIntegerField(
        default=1,
    )

    source_dataset = models.CharField(
        max_length=100,
        blank=True,
    )

    source_license = models.CharField(
        max_length=100,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "external_id"],
                name="unique_learning_item_per_course",
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.primary_knowledge_component_id
            and self.course_id
            and self.primary_knowledge_component.course_id
            != self.course_id
        ):
            raise ValidationError(
                {
                    "primary_knowledge_component": (
                        "The primary knowledge component must belong "
                        "to the same course as the learning item."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.external_id} — "
            f"{self.problem_type or 'Learning item'}"
        )