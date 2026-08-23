"""Tests for environment-driven configuration in config.settings."""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from config.settings import parse_database_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DatabaseConfigTests(SimpleTestCase):
    def test_postgres_url_parses_including_sslmode(self):
        config = parse_database_url(
            "postgresql://school_user:s3cret@db.example.com:5433/school_library"
            "?sslmode=require"
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "school_library")
        self.assertEqual(config["USER"], "school_user")
        self.assertEqual(config["PASSWORD"], "s3cret")
        self.assertEqual(config["HOST"], "db.example.com")
        self.assertEqual(config["OPTIONS"], {"sslmode": "require"})

    def test_legacy_postgres_scheme_accepted(self):
        config = parse_database_url("postgres://u:p@h/dbname")
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "dbname")

    def test_conn_max_age_applied(self):
        config = parse_database_url("postgresql://u:p@h/dbname", conn_max_age=60)
        self.assertEqual(config["CONN_MAX_AGE"], 60)

    def test_sqlite_url(self):
        config = parse_database_url("sqlite:///./db.sqlite3")
        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(config["NAME"], "./db.sqlite3")

    def test_postgres_database_url_boots(self):
        """A PostgreSQL DATABASE_URL boots the settings module.

        The settings module must construct the PostgreSQL backend entry
        without error when DATABASE_URL is set; a live server is not needed
        (no connection is opened at import time).
        """
        env = dict(os.environ)
        env["DATABASE_URL"] = "postgresql://u:p@localhost:5432/school?sslmode=disable"
        result = subprocess.run(
            [sys.executable, "-c",
             "import config.settings as s; "
             "print(s.DATABASES['default']['ENGINE'])"],
            env=env,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("postgresql", result.stdout)


class AuthConfigurationTests(SimpleTestCase):
    def test_custom_user_model_is_configured(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")

    def test_auth_flow_settings_point_to_named_routes(self):
        self.assertEqual(settings.LOGIN_URL, "login")
        self.assertEqual(settings.LOGIN_REDIRECT_URL, "home")
        self.assertEqual(settings.LOGOUT_REDIRECT_URL, "login")