from django.shortcuts import redirect

from accounts.models import User


def home_view(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    if request.user.role == User.Role.PROFESSOR:
        return redirect(
            "courses:professor_dashboard"
        )

    return redirect("learning:practice")