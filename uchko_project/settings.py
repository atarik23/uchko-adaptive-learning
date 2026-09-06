from pathlib import Path
from decouple import config
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

#SECRET_KEY = "django-insecure-change-me-in-production-uchko-demo-key-9e8f7a6b5c4d3e2f1"
SECRET_KEY = config("SECRET_KEY", default="change-me-in-prod")
DEBUG = config("DEBUG", default=True, cast=bool)

#DEBUG = True

#ALLOWED_HOSTS = ["*"]
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=lambda v: [x.strip() for x in v.split(",") if x.strip()]
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "learning",
    "accounts",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "learning:practice"
LOGOUT_REDIRECT_URL = "accounts:login"

ROOT_URLCONF = "uchko_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "uchko_project.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "learning" / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

UCHKO_REPO_ROOT = BASE_DIR
UCHKO_EVENTS_PATH = BASE_DIR / "data" / "cache" / "events.parquet"
UCHKO_USERS_PATH = BASE_DIR / "data" / "cache" / "users.json"
UCHKO_SKILLS_PATH = BASE_DIR / "data" / "content" / "skills.json"
UCHKO_TEMPLATES_PATH = BASE_DIR / "data" / "content" / "templates.json"
UCHKO_SESSION_SUMMARIES_PATH = BASE_DIR / "data" / "cache" / "session_summaries.parquet"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
