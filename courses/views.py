from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

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
        return redirect("learning:practice")

    if request.method == "POST":
        form = EnrollmentCodeForm(request.POST)

        if form.is_valid():
            enrollment_code = form.cleaned_data["enrollment_code"]

            try:
                course = Course.objects.get(enrollment_code=enrollment_code)
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