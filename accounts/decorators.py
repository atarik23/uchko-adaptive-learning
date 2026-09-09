from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden

from .models import User


def student_required(view_function):
    @wraps(view_function)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if request.user.role != User.Role.STUDENT:
            return HttpResponseForbidden(
                "This page is available only to students."
            )

        return view_function(request, *args, **kwargs)

    return wrapped_view


def professor_required(view_function):
    @wraps(view_function)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if request.user.role != User.Role.PROFESSOR:
            return HttpResponseForbidden(
                "This page is available only to professors."
            )

        return view_function(request, *args, **kwargs)

    return wrapped_view