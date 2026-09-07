from django.contrib import admin

from .models import Course, Enrollment, KnowledgeComponent, StudentKnowledgeState, LearningAttempt, LearningSession

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
    search_fields = (
        "code",
        "name",
        "professor__username",
        "professor__email",
    )
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

@admin.register(KnowledgeComponent)
class KnowledgeComponentAdmin(admin.ModelAdmin):
    list_display = (
        "external_id",
        "name",
        "course",
        "parent",
    )
    list_filter = ("course",)
    search_fields = (
        "external_id",
        "name",
        "course__code",
        "course__name",
    )

@admin.register(StudentKnowledgeState)
class StudentKnowledgeStateAdmin(admin.ModelAdmin):
    list_display = (
        "student_display",
        "component_display",
        "course_display",
        "mastery_prob",
        "last_attempt_at",
    )
    list_filter = (
        "enrollment__course",
        "knowledge_component__course",
    )
    search_fields = (
        "enrollment__student__username",
        "enrollment__student__email",
        "knowledge_component__external_id",
        "knowledge_component__name",
        "enrollment__course__code",
        "enrollment__course__name",
    )
    raw_id_fields = (
        "enrollment",
        "knowledge_component",
    )

    def student_display(self, obj):
        return obj.enrollment.student.username

    def component_display(self, obj):
        return obj.knowledge_component.external_id

    def course_display(self, obj):
        return obj.enrollment.course.code

    student_display.short_description = "Student"
    component_display.short_description = "Component"
    course_display.short_description = "Course"

@admin.register(LearningAttempt)
class LearningAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "student_display",
        "component_display",
        "course_display",
        "is_correct",
        "attempted_at",
    )
    list_filter = (
        "is_correct",
        "enrollment__course",
        "knowledge_component__course",
    )
    search_fields = (
        "enrollment__student__username",
        "enrollment__student__email",
        "knowledge_component__external_id",
        "knowledge_component__name",
        "enrollment__course__code",
        "enrollment__course__name",
    )
    raw_id_fields = (
        "enrollment",
        "knowledge_component",
    )
    date_hierarchy = "attempted_at"

    def student_display(self, obj):
        return obj.enrollment.student.username

    def component_display(self, obj):
        return obj.knowledge_component.external_id

    def course_display(self, obj):
        return obj.enrollment.course.code

    student_display.short_description = "Student"
    component_display.short_description = "Component"
    course_display.short_description = "Course"

@admin.register(LearningSession)
class LearningSessionAdmin(admin.ModelAdmin):
    list_display = (
        "student_display",
        "course_display",
        "started_at",
        "ended_at",
        "duration_seconds",
    )
    list_filter = (
        "enrollment__course",
    )
    search_fields = (
        "enrollment__student__username",
        "enrollment__student__email",
        "enrollment__course__code",
        "enrollment__course__name",
    )
    raw_id_fields = ("enrollment",)
    date_hierarchy = "started_at"

    def student_display(self, obj):
        return obj.enrollment.student.username

    def course_display(self, obj):
        return obj.enrollment.course.code

    student_display.short_description = "Student"
    course_display.short_description = "Course"
