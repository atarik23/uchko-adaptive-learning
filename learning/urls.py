from django.urls import path

from . import (
    curriculum_views,
    home_views,
    practice_views,
    progress_views,
    settings_views,
)


app_name = "learning"


urlpatterns = [
    path(
        "",
        home_views.home_view,
        name="account",
    ),
    path(
        "new-session/",
        practice_views.new_session_view,
        name="new_session",
    ),
    path(
        "end-session/",
        practice_views.end_session_view,
        name="end_session",
    ),
    path(
        "practice/",
        practice_views.practice_view,
        name="practice",
    ),
    path(
        "practice/generate/",
        practice_views.generate_question_view,
        name="generate_question",
    ),
    path(
        "practice/submit/",
        practice_views.submit_answer_view,
        name="submit_answer",
    ),
    path(
        "practice/hint/",
        practice_views.request_hint_view,
        name="request_hint",
    ),
    path(
        "practice/explanation/",
        practice_views.request_explanation_view,
        name="request_explanation",
    ),
    path(
        "progress/",
        progress_views.progress_view,
        name="progress",
    ),
    path(
        "curriculum/",
        curriculum_views.curriculum_view,
        name="curriculum",
    ),
    path(
        "settings/",
        settings_views.settings_view,
        name="settings",
    ),
]