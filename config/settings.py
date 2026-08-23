"""
Django settings for the School Virtual Library project.

Environment-driven configuration. Local development uses SQLite by default;
set DATABASE_URL to a PostgreSQL URL to switch backends (production target).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load secrets from .env into the environment (dotenv never overrides
# variables that are already set in the process environment).
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-key-do-not-use-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool("DEBUG", default=True)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local applications
    "common.apps.CommonConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# Local development defaults to SQLite (zero-setup on Windows).
# Set DATABASE_URL to a PostgreSQL URL to use PostgreSQL.
# pgvector support (semantic search) is added in Phase 4 on PostgreSQL.

if os.getenv("DATABASE_URL"):
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                # See also https://www.postgresql.org/docs/current/libpq-connect.html
                "NAME": _parse_db_component(url, "database", "school_library"),
                "USER": _parse_db_component(url, "user", ""),
                "PASSWORD": _parse_db_component(url, "password", ""),
                "HOST": _parse_db_component(url, "host", "localhost"),
                "PORT": _parse_db_component(url, "port", "5432"),
            }
        }
    else:
        raise ValueError(
            "Unsupported DATABASE_URL scheme. Use a PostgreSQL URL "
            "('postgresql://...') or leave DATABASE_URL unset for SQLite."
        )
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


def _parse_db_component(url, component, default):
    """Return a host/user/port/database component from a SQLAlchemy-style
    URL like postgresql://user:password@host:5432/dbname."""
    from urllib.parse import urlparse

    parsed = urlparse(url.replace("postgres://", "postgresql://"))
    mapping = {
        "host": parsed.hostname or default,
        "port": str(parsed.port) if parsed.port else default,
        "user": parsed.username or "",
        "password": parsed.password or "",
        "database": (parsed.path or "/").lstrip("/") or default,
    }
    return mapping[component]


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# User-uploaded document storage. Documents must never be publicly served;
# controlled download views are implemented in a later phase.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"