"""
Django settings for the School Virtual Library project.

Environment-driven configuration. Local development uses SQLite by default;
set DATABASE_URL to a PostgreSQL URL to switch backends (production target).
"""

import os
import sys
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
    "accounts",
    "schools",
    "classes",
    "subjects",
    "students",
    "teachers",
]

# Custom user model. Must remain set before the first migration; changing it
# later requires a full database rebuild.
AUTH_USER_MODEL = "accounts.User"

# Authentication flow
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

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
        "DIRS": [BASE_DIR / "templates"],
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

from urllib.parse import urlparse


def parse_postgresql_url(url):
    """Parse a SQLAlchemy-style PostgreSQL URL into a Django DATABASES entry.

    Accepts 'postgresql://user:password@host:port/dbname' and the legacy
    'postgres://' scheme. Missing host/port fall back to libpq-friendly
    defaults. Raises ValueError when required parts are absent.
    """
    parsed = urlparse(url.replace("postgres://", "postgresql://", 1))
    if parsed.scheme != "postgresql":
        raise ValueError(
            "Unsupported DATABASE_URL scheme. Use a PostgreSQL URL "
            "('postgresql://...') or leave DATABASE_URL unset for SQLite."
        )
    name = (parsed.path or "").lstrip("/")
    if not name:
        raise ValueError("DATABASE_URL must include a database name.")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "localhost",
        "PORT": str(parsed.port) if parsed.port else "",
    }


_database_url = os.getenv("DATABASE_URL")
if _database_url:
    DATABASES = {"default": parse_postgresql_url(_database_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


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

# Fast (insecure) hashing during test runs only; never used for real accounts.
if len(sys.argv) > 1 and sys.argv[1] == "test":
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


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
STATICFILES_DIRS = [BASE_DIR / "static"]

# User-uploaded document storage. Documents must never be publicly served;
# controlled download views are implemented in a later phase.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"