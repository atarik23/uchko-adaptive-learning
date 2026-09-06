from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm

from .models import User


class StudentRegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=150,
        required=True,
        label="First name",
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label="Last name",
    )
    email = forms.EmailField(
        required=True,
        label="Email address",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "A user with this email address already exists."
            )

        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.STUDENT
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()

        return user


class LoginForm(forms.Form):
    identifier = forms.CharField(
        max_length=254,
        label="Username or email",
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Password",
    )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user_cache = None

    def clean(self):
        cleaned_data = super().clean()

        identifier = (cleaned_data.get("identifier") or "").strip()
        password = cleaned_data.get("password")

        if identifier and password:
            user = User.objects.filter(username__iexact=identifier).first()

            if user is None:
                user = User.objects.filter(email__iexact=identifier).first()

            if user is None:
                raise forms.ValidationError(
                    "Invalid username/email or password."
                )

            self.user_cache = authenticate(
                self.request,
                username=user.username,
                password=password,
            )

            if self.user_cache is None:
                raise forms.ValidationError(
                    "Invalid username/email or password."
                )

            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    "This account is inactive."
                )

        return cleaned_data

    def get_user(self):
        return self.user_cache