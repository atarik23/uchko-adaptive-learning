from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.decorators import professor_required, student_required
from accounts.models import User

from .forms import EnrollmentCodeForm
from .models import Course, Enrollment


@login_required
@require_http_methods(["GET", "POST"])
def enroll_view(request):
    if request.user.role != User.Role.STUDENT:
        messages.error(
            request,
            "Only student accounts can enroll in a course.",
        )
        return redirect("courses:professor_dashboard")

    if request.method == "POST":
        form = EnrollmentCodeForm(request.POST)

        if form.is_valid():
            enrollment_code = form.cleaned_data["enrollment_code"]

            try:
                course = Course.objects.get(
                    enrollment_code=enrollment_code
                )
            except Course.DoesNotExist:
                form.add_error(
                    "enrollment_code",
                    "No course was found for that enrollment code.",
                )
            else:
                if not course.is_active:
                    form.add_error(
                        "enrollment_code",
                        "This course is not currently accepting enrollments.",
                    )
                else:
                    enrollment, created = Enrollment.objects.get_or_create(
                        course=course,
                        student=request.user,
                        defaults={"is_active": True},
                    )

                    if created:
                        messages.success(
                            request,
                            f"You have been enrolled in {course.name}.",
                        )
                    elif enrollment.is_active:
                        messages.info(
                            request,
                            f"You are already enrolled in {course.name}.",
                        )
                    else:
                        enrollment.is_active = True
                        enrollment.save(update_fields=["is_active"])

                        messages.success(
                            request,
                            f"Your enrollment in {course.name} was reactivated.",
                        )

                    return redirect("learning:practice")
    else:
        form = EnrollmentCodeForm()

    return render(
        request,
        "courses/enroll.html",
        {"form": form},
    )


@professor_required
def professor_dashboard_view(request):
    enrollment_summaries = (
        Enrollment.objects
        .select_related("student")
        .annotate(
            attempt_count=Count(
                "learning_attempts",
                distinct=True,
            ),
            average_accuracy=Avg(
                "learning_attempts__answer_is_correct",
            ),
            last_activity=Max(
                "learning_attempts__attempted_at",
            ),
            session_count=Count(
                "learning_sessions",
                distinct=True,
            ),
        )
        .order_by(
            "student__last_name",
            "student__first_name",
            "student__username",
        )
    )

    courses = (
        Course.objects
        .filter(professor=request.user)
        .prefetch_related(
            Prefetch(
                "enrollments",
                queryset=enrollment_summaries,
                to_attr="student_summaries",
            )
        )
        .order_by("code")
    )

    return render(
        request,
        "courses/professor_dashboard.html",
        {
            "courses": courses,
            "active_tab": "professor_dashboard",
        },
    )


@professor_required
def professor_student_detail_view(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related(
            "student",
            "course",
        ),
        id=enrollment_id,
        course__professor=request.user,
    )

    knowledge_states = (
        enrollment.knowledge_states
        .select_related("knowledge_component")
        .order_by("knowledge_component__name")
    )

    recent_attempts = (
        enrollment.learning_attempts
        .select_related("knowledge_component", "session")
        .order_by("-attempted_at")[:20]
    )

    learning_sessions = (
        enrollment.learning_sessions
        .select_related("goal_component")
        .order_by("-started_at")[:20]
    )

    attempt_statistics = enrollment.learning_attempts.aggregate(
        total_attempts=Count("id"),
        average_accuracy=Avg("answer_is_correct"),
        last_activity=Max("attempted_at"),
    )

    return render(
        request,
        "courses/professor_student_detail.html",
        {
            "enrollment": enrollment,
            "student": enrollment.student,
            "course": enrollment.course,
            "knowledge_states": knowledge_states,
            "recent_attempts": recent_attempts,
            "learning_sessions": learning_sessions,
            "attempt_statistics": attempt_statistics,
            "active_tab": "professor_dashboard",
        },
    )


@student_required
def student_dashboard_view(request):
    enrollments = (
        Enrollment.objects
        .filter(student=request.user)
        .select_related(
            "course",
            "course__professor",
        )
        .annotate(
            attempt_count=Count(
                "learning_attempts",
                distinct=True,
            ),
            average_accuracy=Avg(
                "learning_attempts__answer_is_correct",
            ),
            session_count=Count(
                "learning_sessions",
                distinct=True,
            ),
            last_activity=Max(
                "learning_attempts__attempted_at",
            ),
        )
        .prefetch_related(
            "knowledge_states__knowledge_component",
            "learning_attempts__knowledge_component",
            "learning_sessions__goal_component",
        )
        .order_by("course__code")
    )

    return render(
        request,
        "courses/student_dashboard.html",
        {
            "enrollments": enrollments,
            "active_tab": "student_dashboard",
        },
    )