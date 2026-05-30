"""
Django settings for wsia project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-change-me-before-production")
DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1", "t")
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    # Local
    "core",
    "reports",
    "api",
    "analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "wsia.urls"

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

WSGI_APPLICATION = "wsia.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_db_url = os.environ.get("DATABASE_URL", "")

if _db_url and _db_url.startswith("postgres"):
    import re

    _m = re.match(
        r"postgres(?:ql)?://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:/]+)"
        r"(?::(?P<port>\d+))?/(?P<name>.+)",
        _db_url,
    )
    if _m:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": _m.group("name"),
                "USER": _m.group("user"),
                "PASSWORD": _m.group("password"),
                "HOST": _m.group("host"),
                "PORT": _m.group("port") or "5432",
            }
        }
    else:
        raise ValueError(f"Could not parse DATABASE_URL: {_db_url!r}")
else:
    # Fall back to SQLite for local development without a DATABASE_URL
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "WSIA Intelligence API",
    "DESCRIPTION": "Web Security Intelligence Architecture API Documentation",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SECURITY": [{"bearerAuth": []}],
    "COMPONENTS": {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
    },
}

# ---------------------------------------------------------------------------
# Celery (Phase 5+)
# ---------------------------------------------------------------------------
# Default broker: memory:// works without Redis — set CELERY_BROKER_URL=redis://...
# in .env when Redis is available.

_default_broker = os.environ.get("CELERY_BROKER_URL", "memory://")
_default_backend = os.environ.get("CELERY_RESULT_BACKEND", "cache+memory://")

CELERY_BROKER_URL = _default_broker
CELERY_RESULT_BACKEND = _default_backend
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
# Silence Celery 6.0 deprecation warning about broker_connection_retry
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True



# Celery Beat — periodic task schedule
# Requires: celery -A wsia beat --loglevel=info
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Full scrape + normalise pipeline — every 6 hours
    "run-pipeline-every-6h": {
        "task": "analytics.tasks.run_pipeline",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"expires": 3600},   # drop if still queued after 1h
    },
    # Normalise any records that failed the first pass — daily at 03:00 UTC
    "normalize-unprocessed-daily": {
        "task": "analytics.tasks.normalize_unprocessed",
        "schedule": crontab(minute=0, hour=3),
        "options": {"expires": 7200},
    },
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "reports": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "analytics": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "api": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
