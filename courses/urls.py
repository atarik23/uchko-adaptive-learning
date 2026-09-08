from django.urls import path
from . import views

app_name = "courses"

urlpatterns = [
    path(
        "professor/dashboard/",
        views.professor_dashboard_view,
        name="professor_dashboard",
    ),
    path(
        "professor/students/<int:enrollment_id>/",
        views.professor_student_detail_view,
        name="professor_student_detail",
    ),
    path(
        "enroll/",
        views.enroll_view,
        name="enroll",
    ),
]