import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
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
        default=0.0,
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

    session = models.ForeignKey(
    "LearningSession",
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="learning_attempts",
    )

    is_correct = models.BooleanField()

    attempted_at = models.DateTimeField()

    context = models.JSONField(
        default=dict,
        blank=True,
    )

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

        # Opcionalna dodatna validacija: ako postoje attempti,
        # provjeri da li su svi iz istog kursa kao enrollment.
        if self.pk:
            attempts = self.learning_attempts.all()
            if attempts.exists():
                for attempt in attempts:
                    if attempt.enrollment.course_id != self.enrollment.course_id:
                        raise ValidationError(
                            "All attempts in a session must belong to the same course as the session's enrollment."
                        )

    def save(self, *args, **kwargs):
        # Ako su oba vremena postavljena, izračunaj trajanje
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        duration = f"{self.duration_seconds}s" if self.duration_seconds is not None else "ongoing"
        return (
            f"{self.enrollment.student.username} — "
            f"{self.enrollment.course.code} — "
            f"{duration} — {self.started_at}"
        )
