"""
Django settings for the School Virtual Library project.

Environment-driven configuration. Local development uses SQLite by default;
set DATABASE_URL to a PostgreSQL URL to switch backends (production target).
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
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


DEV_SECRET_KEY = "dev-insecure-secret-key-do-not-use-in-production"


def base_security_defaults(debug):
    """DEBUG-dependent security defaults, kept in one testable place.

    Production is the safe default: everything below turns on unless DEBUG
    is enabled. Every value can still be forced via environment.
    """
    return {
        "SECURE_SSL_REDIRECT": not debug,
        "SECURE_HSTS_SECONDS": 31536000 if not debug else 0,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": not debug,
        "SECURE_HSTS_PRELOAD": not debug,
        "SESSION_COOKIE_SECURE": not debug,
        "CSRF_COOKIE_SECURE": not debug,
        "SESSION_EXPIRE_AT_BROWSER_CLOSE": not debug,
    }


def validate_run_mode(debug, secret_key, allowed_hosts):
    """Refuse to boot in production-like mode with development credentials."""
    if debug:
        return
    if secret_key == DEV_SECRET_KEY:
        raise ImproperlyConfigured(
            "SECRET_KEY must not be the development default when DEBUG=False."
        )
    if not allowed_hosts:
        raise ImproperlyConfigured("ALLOWED_HOSTS must not be empty when DEBUG=False.")


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY", DEV_SECRET_KEY)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool("DEBUG", default=True)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

# Production security headers / cookies: enabled by default unless DEBUG,
# all env-overridable (AGENTS sections 6/7).
_secure_defaults = base_security_defaults(DEBUG)
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", default=_secure_defaults["SECURE_SSL_REDIRECT"])
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", str(_secure_defaults["SECURE_HSTS_SECONDS"])))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=_secure_defaults["SECURE_HSTS_INCLUDE_SUBDOMAINS"]
)
SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", default=_secure_defaults["SECURE_HSTS_PRELOAD"])
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", default=_secure_defaults["SESSION_COOKIE_SECURE"])
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE", default=_secure_defaults["CSRF_COOKIE_SECURE"])
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

validate_run_mode(DEBUG, SECRET_KEY, ALLOWED_HOSTS)


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
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "common.middleware.IdleSessionMiddleware",
    "common.middleware.MustChangePasswordMiddleware",
    # After the auth stack so it can override the session language with the
    # signed-in user's saved preference (WP7 bilingual UI).
    "common.middleware.UserLanguageMiddleware",
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

LANGUAGE_CODE = "en"

# WP7 bilingual: the school serves anglophone and francophone sections, so the
# UI and AI answers follow the user's language (per-user preference, with a
# session fallback for the login screen). Content itself (resources, questions)
# is tagged en/fr so each section can filter what it sees.
LANGUAGES = [
    ("en", "English"),
    ("fr", "Français"),
]

# Compiled catalog: locale/fr/LC_MESSAGES/django.mo (built from django.po with
# Babel, since the Windows dev image has no GNU gettext binaries).
LOCALE_PATHS = [BASE_DIR / "locale"]

# School is in Cameroon; every date-boundary query runs in local time.
TIME_ZONE = "Africa/Douala"

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
# Keep Django's request/memory ceilings aligned with the library cap so a
# single upload larger than the cap is rejected before file handling begins.
FILE_UPLOAD_MAX_MEMORY_SIZE = LIBRARY_MAX_UPLOAD_MB * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = LIBRARY_MAX_UPLOAD_MB * 1024 * 1024

# Library download abuse control (WP3): per-minute burst and per-day cap,
# enforced against ResourceAccessEvent rows. Superusers are exempt.
LIBRARY_DOWNLOAD_PER_MINUTE = int(os.getenv("LIBRARY_DOWNLOAD_PER_MINUTE", "10"))
LIBRARY_DOWNLOAD_DAILY_CAP = int(os.getenv("LIBRARY_DOWNLOAD_DAILY_CAP", "50"))

# Reverse-proxy internal file serving (WP3): emit X-Accel-Redirect instead of
# streaming from the app server when LIBRARY_XACCEL_ENABLED is set.
LIBRARY_XACCEL_ENABLED = _env_bool("LIBRARY_XACCEL_ENABLED", default=False)
LIBRARY_INTERNAL_PATH_PREFIX = os.getenv("LIBRARY_INTERNAL_PATH_PREFIX", "/internal")

# Document processing. The queue is database-backed (ProcessingJob rows) so
# it runs without Redis; a worker drains it via `process_documents`. When
# DOCUMENTS_INLINE_PROCESSING is True, jobs run synchronously at upload time
# (convenient for tests and tiny files; not for production).
DOCUMENTS_INLINE_PROCESSING = False
DOCUMENTS_CHUNK_SIZE = 1200
DOCUMENTS_CHUNK_OVERLAP = 150
DOCUMENTS_MAX_ATTEMPTS = 3
DOCUMENTS_MAX_PAGES = 2000

# OCR (WP4). The real engine requires Tesseract + Ghostscript binaries for
# ocrmypdf; when they are missing the pipeline marks pages needs_ocr and
# carries on instead of failing (text is never fabricated). Tests inject a
# deterministic fake engine via DOCUMENTS_OCR_FAKE_ENGINE.
DOCUMENTS_OCR_TIMEOUT_SECONDS = int(os.getenv("DOCUMENTS_OCR_TIMEOUT_SECONDS", "300"))
DOCUMENTS_OCR_MAX_PAGES = int(os.getenv("DOCUMENTS_OCR_MAX_PAGES", "500"))
DOCUMENTS_OCR_LANGUAGES = os.getenv("DOCUMENTS_OCR_LANGUAGES", "eng,fra")
DOCUMENTS_OCR_FAKE_ENGINE = _env_bool("DOCUMENTS_OCR_FAKE_ENGINE", default=False)
DOCUMENTS_OCR_FAKE_CONFIDENCE = float(os.getenv("DOCUMENTS_OCR_FAKE_CONFIDENCE", "0.9"))
DOCUMENTS_OCR_FAKE_EMPTY = _env_bool("DOCUMENTS_OCR_FAKE_EMPTY", default=False)
DOCUMENTS_OCR_FAKE_SLEEP = float(os.getenv("DOCUMENTS_OCR_FAKE_SLEEP", "0"))

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
# PostgreSQL/pgvector dimension for the vector column (0 disables the SQL
# ranking path; the SQLite dev fallback is Python cosine).
SEARCH_PGVECTOR_DIM = int(os.getenv("SEARCH_PGVECTOR_DIM", "768"))

# AI Librarian (Phase 5). Retrieved text is DATA, never instructions; the
# answer must cite only the sources actually provided in the context.
RAG_TOP_K = 8
RAG_MAX_CONTEXT_CHARS = 6000
# v2: system prompt now adds a user-language instruction (WP7); the version
# participates in answer-cache keys so a switch invalidates stale wording.
RAG_PROMPT_VERSION = "rag-v2"
STUDY_PROMPT_VERSION = "study-v2"
RAG_USE_CACHE = _env_bool("RAG_USE_CACHE", default=True)
RAG_CACHE_TTL = int(os.getenv("RAG_CACHE_TTL", "86400"))
AI_EMBEDDING_QUERY_CACHE_TTL = int(os.getenv("AI_EMBEDDING_QUERY_CACHE_TTL", "86400"))

# Per-school AI budgets (WP5), counted on AIRequestLog. 0 = unlimited.
AI_BUDGET_DAILY_REQUESTS = int(os.getenv("AI_BUDGET_DAILY_REQUESTS", "0"))
AI_BUDGET_MONTHLY_REQUESTS = int(os.getenv("AI_BUDGET_MONTHLY_REQUESTS", "0"))
AI_BUDGET_DAILY_TOKENS = int(os.getenv("AI_BUDGET_DAILY_TOKENS", "0"))
AI_BUDGET_MONTHLY_TOKENS = int(os.getenv("AI_BUDGET_MONTHLY_TOKENS", "0"))

# Per-resource chunk cap and per-school storage quota (WP5).
DOCUMENTS_MAX_CHUNKS = int(os.getenv("DOCUMENTS_MAX_CHUNKS", "1000"))
SCHOOL_STORAGE_QUOTA_MB = int(os.getenv("SCHOOL_STORAGE_QUOTA_MB", "5000"))
AI_RATE_LIMIT_PER_MINUTE = 10
# Atomic cache-counter rate limiting (WP2) - a Redis cache is shared across
# processes; locmem is per-process. Set False to keep the DB-count path
# (settings_test pins this off for deterministic tests).
AI_RATE_LIMIT_USE_CACHE = _env_bool("AI_RATE_LIMIT_USE_CACHE", default=True)
# Superusers are NOT exempt by default; opt in explicitly per deployment.
AI_RATE_LIMIT_EXEMPT_SUPERUSER = _env_bool("AI_RATE_LIMIT_EXEMPT_SUPERUSER", default=False)

# Cache. Redis via REDIS_URL when configured; locmem otherwise. Rate limiting
# uses cache counters (atomic) with the DB count as a fallback.
REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": "svl",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "svl-local",
        }
    }

# Sessions (AGENTS section 6: idle expiry, shared lab machines assumed).
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", "7200"))
SESSION_IDLE_SECONDS = int(os.getenv("SESSION_IDLE_SECONDS", "1800"))
SESSION_EXPIRE_AT_BROWSER_CLOSE = _env_bool(
    "SESSION_EXPIRE_AT_BROWSER_CLOSE",
    default=_secure_defaults["SESSION_EXPIRE_AT_BROWSER_CLOSE"],
)

# Login lockout (WP3): exponential backoff keyed on username AND IP.
LOGIN_LOCKOUT_BASE_SECONDS = int(os.getenv("LOGIN_LOCKOUT_BASE_SECONDS", "5"))
LOGIN_LOCKOUT_MAX_SECONDS = int(os.getenv("LOGIN_LOCKOUT_MAX_SECONDS", "300"))

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
# WP6 reliability: channel enablement (also admin kill switch), per-phone
# daily outbound cap, and the Meta free-form reply window in hours.
WHATSAPP_ENABLED = _env_bool("WHATSAPP_ENABLED", default=True)
WHATSAPP_DAILY_MESSAGE_CAP = int(os.getenv("WHATSAPP_DAILY_MESSAGE_CAP", "20"))
WHATSAPP_MESSAGE_WINDOW_HOURS = int(os.getenv("WHATSAPP_MESSAGE_WINDOW_HOURS", "24"))

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