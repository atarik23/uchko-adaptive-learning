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
                {"professor": "The course professor must have the professor role."}
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
                {"student": "Only users with the student role can be enrolled in a course."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.username} enrolled in {self.course.code}"
