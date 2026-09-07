from django.contrib import admin

from .models import Course, Enrollment


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "professor",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name", "professor__username", "professor__email")
    readonly_fields = ("enrollment_code", "created_at")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        "course",
        "student",
        "is_active",
        "enrolled_at",
    )
    list_filter = ("is_active", "course")
    search_fields = (
        "course__code",
        "course__name",
        "student__username",
        "student__email",
    )
    readonly_fields = ("enrolled_at",)
