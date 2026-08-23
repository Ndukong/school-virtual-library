"""Tests for environment-driven configuration in config.settings."""

from django.test import SimpleTestCase

from config.settings import parse_postgresql_url


class ParsePostgresqlUrlTests(SimpleTestCase):
    def test_full_url_is_parsed(self):
        config = parse_postgresql_url(
            "postgresql://school_user:s3cret@db.example.com:6543/school_library"
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "school_library")
        self.assertEqual(config["USER"], "school_user")
        self.assertEqual(config["PASSWORD"], "s3cret")
        self.assertEqual(config["HOST"], "db.example.com")
        self.assertEqual(config["PORT"], "6543")

    def test_missing_host_and_port_use_defaults(self):
        config = parse_postgresql_url("postgresql://user:pass@/school_library")
        self.assertEqual(config["HOST"], "localhost")
        self.assertEqual(config["PORT"], "")
        self.assertEqual(config["NAME"], "school_library")

    def test_legacy_postgres_scheme_is_accepted(self):
        config = parse_postgresql_url("postgres://u:p@h:5432/dbname")
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "dbname")

    def test_url_without_password_is_supported(self):
        config = parse_postgresql_url("postgresql://u@h:5432/dbname")
        self.assertEqual(config["USER"], "u")
        self.assertEqual(config["PASSWORD"], "")

    def test_missing_database_name_raises(self):
        with self.assertRaises(ValueError):
            parse_postgresql_url("postgresql://u:p@h:5432/")
        with self.assertRaises(ValueError):
            parse_postgresql_url("postgresql://u:p@h:5432")

    def test_unsupported_scheme_raises(self):
        with self.assertRaises(ValueError):
            parse_postgresql_url("mysql://u:p@h:3306/dbname")
