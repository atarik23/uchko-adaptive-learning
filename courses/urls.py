from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("enroll/", views.enroll_view, name="enroll"),
]
