from django.urls import path

from . import (
    curriculum_views,
    practice_views,
    progress_views,
    views,
)

app_name = "learning"

urlpatterns = [
    path("", views.account_view, name="account"),
    path("create-user/", views.create_user_view, name="create_user"),
    path("select-user/", views.select_user_view, name="select_user"),
    path("logout/", views.logout_view, name="logout"),
    path("new-session/", practice_views.new_session_view, name="new_session",),
    path("end-session/", practice_views.end_session_view, name="end_session",),
    path("practice/", practice_views.practice_view, name="practice",),
    path("practice/generate/", practice_views.generate_question_view, name="generate_question",),
    path("practice/submit/", practice_views.submit_answer_view, name="submit_answer",),
    path("practice/hint/", practice_views.request_hint_view, name="request_hint",),
    path("practice/explanation/", practice_views.request_explanation_view, name="request_explanation",),
    path("practice/set-goal/", views.set_goal_view, name="set_goal"),
    path("practice/toggle-adaptive/", views.toggle_adaptive_view, name="toggle_adaptive"),
    path("practice/manual/", views.set_manual_view, name="set_manual"),
    path("progress/", progress_views.progress_view, name="progress",),
    path("curriculum/", curriculum_views.curriculum_view, name="curriculum",),
    path("curriculum/graph.png", views.curriculum_graph_view, name="curriculum_graph"),
    path("settings/", views.settings_view, name="settings"),
    path("export/session.csv", views.export_session_csv, name="export_session_csv"),
]
