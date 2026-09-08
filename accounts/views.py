from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from learning import services as learning_services

from .forms import LoginForm, StudentRegistrationForm
from .models import User


def redirect_for_user(user):
    """
    Redirect an authenticated user to the correct area
    based on their Uchko role.
    """
    if user.role == User.Role.PROFESSOR:
        return redirect("courses:professor_dashboard")

    return redirect("learning:practice")


@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        return redirect_for_user(request.user)

    if request.method == "POST":
        form = StudentRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)

            learning_services.initialize_authenticated_runtime_state(
                request
            )

            return redirect_for_user(user)
    else:
        form = StudentRegistrationForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect_for_user(request.user)

    if request.method == "POST":
        form = LoginForm(request, request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Only students need the temporary practice runtime state.
            if user.role == User.Role.STUDENT:
                learning_services.initialize_authenticated_runtime_state(
                    request
                )

            return redirect_for_user(user)
    else:
        form = LoginForm(request)

    return render(
        request,
        "accounts/login.html",
        {"form": form},
    )


@require_POST
@login_required
def logout_view(request):
    learning_services.clear_authenticated_runtime_state(request)
    logout(request)

    return redirect("accounts:login")