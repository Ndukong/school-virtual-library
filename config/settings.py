"""
Django settings for the School Virtual Library project.

Environment-driven configuration. Local development uses SQLite by default;
set DATABASE_URL to a PostgreSQL URL to switch backends (production target).
"""

import os
from pathlib import Path

import dj_database_url
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
    "library",
    "documents",
    "ai",
    "search",
    "question_bank",
    "examinations",
    "learning",
    "whatsapp",
    "pwa",
    "reports",
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
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
                "pwa.context_processors.pwa_enabled",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# Local development defaults to SQLite (zero-setup on Windows). Set
# DATABASE_URL to switch backends (e.g. PostgreSQL). Parsing is delegated to
# dj-database-url so PostgreSQL options survive, including `?sslmode=require`
# and the legacy `postgres://` scheme. CONN_MAX_AGE is env-driven.
_DATABASE_CONN_MAX_AGE = int(os.getenv("DATABASE_CONN_MAX_AGE", "60"))


def parse_database_url(url, conn_max_age=_DATABASE_CONN_MAX_AGE):
    """A Django DATABASES 'default' entry built from a DATABASE_URL."""
    return dj_database_url.parse(url, conn_max_age=conn_max_age)


_DATABASE_URL = os.getenv("DATABASE_URL")
if _DATABASE_URL:
    DATABASES = {"default": parse_database_url(_DATABASE_URL)}
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

# Library upload limits. Uploaded files are untrusted input: the library app
# additionally validates extension, size, and file content signature.
LIBRARY_MAX_UPLOAD_MB = 100

# Document processing. The queue is database-backed (ProcessingJob rows) so
# it runs without Redis; a worker drains it via `process_documents`. When
# DOCUMENTS_INLINE_PROCESSING is True, jobs run synchronously at upload time
# (convenient for tests and tiny files; not for production).
DOCUMENTS_INLINE_PROCESSING = False
DOCUMENTS_CHUNK_SIZE = 1200
DOCUMENTS_CHUNK_OVERLAP = 150
DOCUMENTS_MAX_ATTEMPTS = 3
DOCUMENTS_MAX_PAGES = 2000

# AI provider abstraction (AGENTS.md section 13). Provider-specific SDKs are
# never used outside the ai app. "mock" runs offline with deterministic
# vectors (tests/dev); "openai_compatible" targets NVIDIA NIM and any router
# exposing OpenAI-style endpoints; "gemini" uses Google's Generative Language
# API. Groq serves chat only (no embeddings endpoint) - reserve it for Phase 5.
AI_PROVIDER = os.getenv("AI_PROVIDER", "mock")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_EMBEDDING_MODEL = os.getenv("AI_EMBEDDING_MODEL", "mock-embed-small")
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "2"))

# Chat generation (Phase 5). Groq is the default chat provider; gemini and
# openai_compatible (NVIDIA NIM / routers) are selectable backups. The
# factory applies per-provider default models unless AI_CHAT_MODEL is set.
AI_CHAT_PROVIDER = os.getenv("AI_CHAT_PROVIDER", "groq")
AI_CHAT_MODEL = os.getenv("AI_CHAT_MODEL", "")

# Search behaviour (Phase 4). Vectors are stored with their model name so a
# model switch triggers re-embedding instead of mixing vector spaces.
SEARCH_SEMANTIC_TOP_K = 12
SEARCH_KEYWORD_TOP_K = 12
SEARCH_MIN_SIMILARITY = 0.15

# AI Librarian (Phase 5). Retrieved text is DATA, never instructions; the
# answer must cite only the sources actually provided in the context.
RAG_TOP_K = 8
RAG_MAX_CONTEXT_CHARS = 6000
RAG_PROMPT_VERSION = "rag-v1"
STUDY_PROMPT_VERSION = "study-v1"
AI_RATE_LIMIT_PER_MINUTE = 10

# Student practice (Phase 9). Answers are withheld until submission;
# progress is strictly private to the student.
PRACTICE_DEFAULT_SIZE = 5
PRACTICE_MAX_SIZE = 20

# WhatsApp channel (Phase 10). WHATSAPP_PROVIDER=console logs outbound text
# (dev/tests) and never touches the network; =meta posts to the Graph API.
# The webhook verifies X-Hub-Signature-256 with WHATSAPP_APP_SECRET and FAILS
# CLOSED when the secret is unset outside DEBUG.
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "console")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v21.0")
WHATSAPP_RATE_LIMIT_PER_MINUTE = int(os.getenv("WHATSAPP_RATE_LIMIT_PER_MINUTE", "10"))
WHATSAPP_LINK_CODE_MINUTES = int(os.getenv("WHATSAPP_LINK_CODE_MINUTES", "15"))

# PWA (Phase 11). Registers the service worker (its network-first strategy
# only caches the static shell; authenticated content and files are never
# stored offline).
PWA_ENABLED = _env_bool("PWA_ENABLED", default=True)

# Logging: console + rotating file. Level from LOG_LEVEL. The verbose
# formatter emits timestamp/logger/message only - never request bodies,
# headers, or secrets.
_LOG_DIR = BASE_DIR / "logs"
_LOG_DIR.mkdir(exist_ok=True)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {funcName} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": _LOG_DIR / "svl.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console", "file"], "level": LOG_LEVEL},
}


# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"