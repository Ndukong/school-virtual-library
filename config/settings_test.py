"""Test settings.

Inherits everything from config.settings, then forces the test environment
to be offline, deterministic and cheap.

    python manage.py test --settings=config.settings_test

This file replaces the sys.argv-based PASSWORD_HASHERS hack in
config/settings.py (removed in Work Package 1), which broke under pytest,
--parallel, and any non-default runner.

Rules this file obeys (AGENTS.md):
- It never weakens a security control that a test asserts.
- It never points at a real AI or WhatsApp provider, so a populated .env
  cannot cause a test run to hit the network or spend tokens.
"""

import tempfile
from pathlib import Path

from config.settings import *

# --- Identity -------------------------------------------------------------
# Explicit, obviously-fake values so tests never depend on a developer's .env.
SECRET_KEY = "test-only-not-a-secret-and-never-used-anywhere-real"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# --- Speed ----------------------------------------------------------------
# Fast (insecure) hashing for fixtures only. Never reaches a real account.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# --- Never touch the network ---------------------------------------------
# A developer with a real Groq or NVIDIA key in .env must not be able to
# spend money by running the test suite.
AI_PROVIDER = "mock"
AI_CHAT_PROVIDER = "mock"
AI_API_KEY = ""
AI_BASE_URL = ""
AI_EMBEDDING_MODEL = "mock-embed-small"
AI_CHAT_MODEL = ""

WHATSAPP_PROVIDER = "console"
WHATSAPP_ACCESS_TOKEN = ""
WHATSAPP_PHONE_NUMBER_ID = ""
# Signature verification must stay ENABLED in tests. Tests that exercise
# the webhook supply their own secret via override_settings; leaving this
# empty keeps the fail-closed path under test.
WHATSAPP_APP_SECRET = ""

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Rate limiting uses the deterministic DB-count path in the suite; the atomic
# cache-counter path is exercised by dedicated tests at ai.tests with
# override_settings(AI_RATE_LIMIT_USE_CACHE=True).
AI_RATE_LIMIT_USE_CACHE = False

# --- Isolation ------------------------------------------------------------
# Uploads during tests go to a scratch directory, never the real media/.
# Safe to delete at any time.
MEDIA_ROOT = Path(tempfile.gettempdir()) / "svl-test-media"

# Explicit local cache. Rate limiting moves onto cache counters in
# Work Package 2; a per-process locmem cache keeps tests independent.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "svl-test-cache",
    }
}

# --- Output ---------------------------------------------------------------
# Keep test output readable once Work Package 1 adds a real LOGGING config.
# Raise this to DEBUG when you are actually chasing something.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "ERROR"},
}

# --- Deliberately NOT overridden -----------------------------------------
# DOCUMENTS_INLINE_PROCESSING stays False. Some existing tests assert that
# work is QUEUED rather than run at upload time; flipping it globally here
# would silently change what those tests prove. Tests that want inline
# behaviour should use override_settings.
#
# Rate limits, upload caps and chunk sizes stay at production values so the
# suite exercises the real boundaries.