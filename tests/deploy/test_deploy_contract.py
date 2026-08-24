"""WP10: deployment contract test.

Keeps the docker share honest without needing Docker on the dev box:
every environment key the compose file or the .env.prod.example template
mentions must actually be consumed by config/settings.py, the compose must
wire the expected services/healthchecks, the backup/restore scripts must look
like they will do the right thing, and the CI workflow must run the full gate.
"""

import re
from pathlib import Path

import yaml
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parent.parent.parent

SETTINGS = ROOT / "config" / "settings.py"
COMPOSE = ROOT / "deploy" / "docker-compose.prod.yml"
ENV_TEMPLATE = ROOT / "deploy" / ".env.prod.example"
CI = ROOT / ".github" / "workflows" / "ci.yml"
BACKUP = ROOT / "deploy" / "backup.sh"
RESTORE = ROOT / "deploy" / "restore.sh"
REQS_DEV = ROOT / "requirements-dev.txt"

# Env keys consumed by the docker-compose *runtime* itself, not by Django
# settings (they configure the database container and Caddy).
_COMPOSE_ONLY_KEYS = {"POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DOMAIN"}


def _settings_env_keys():
    text = SETTINGS.read_text(encoding="utf-8")
    patterns = [
        re.compile(r"os\.getenv\(\s*[\"']([A-Z0-9_]+)[\"']"),
        re.compile(r"_env_bool\(\s*[\"']([A-Z0-9_]+)[\"']"),
    ]
    keys = set()
    for pattern in patterns:
        keys.update(pattern.findall(text))
    return keys


class DeployStackContractTests(SimpleTestCase):
    def test_compose_defines_the_expected_services(self):
        stack = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        services = set(stack["services"])
        self.assertTrue(
            {"db", "web", "worker_documents", "worker_whatsapp", "caddy"} <= services
        )
        db = stack["services"]["db"]
        self.assertTrue(db["image"].startswith("pgvector/pgvector:pg16"))
        self.assertIn("80:80", stack["services"]["caddy"]["ports"])
        self.assertIn("443:443", stack["services"]["caddy"]["ports"])
        # The web container healthchecks against the app's /healthz/ probe.
        healthcheck = str(stack["services"]["web"]["healthcheck"])
        self.assertIn("/healthz/", healthcheck)
        # Worker images run the documented queue loops once db+redis are up.
        self.assertEqual(
            stack["services"]["worker_documents"]["command"],
            ["python", "manage.py", "process_documents", "--loop"],
        )
        self.assertEqual(
            stack["services"]["worker_whatsapp"]["command"],
            ["python", "manage.py", "process_whatsapp", "--loop"],
        )

    def test_compose_environment_keys_are_settings_consumed(self):
        stack = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        settings_keys = _settings_env_keys()
        for service_name in ("web", "worker_documents", "worker_whatsapp"):
            env = stack["services"][service_name]["environment"]
            for key in env:
                self.assertIn(
                    key,
                    settings_keys | {"DJANGO_SETTINGS_MODULE", "DATABASE_URL", "REDIS_URL", "DEBUG"},
                    f"{service_name} references an env key settings.py does not read: {key}",
                )
            self.assertEqual(
                stack["services"][service_name].get("env_file"), ".env.prod"
            )

    def test_env_template_keys_are_consumed_by_settings(self):
        settings_keys = _settings_env_keys()
        template = ENV_TEMPLATE.read_text(encoding="utf-8")
        for line in template.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if key.startswith("$"):
                continue
            self.assertIn(
                key,
                settings_keys | _COMPOSE_ONLY_KEYS,
                f".env.prod.example key not consumed anywhere: {key}",
            )

    def test_database_url_wiring_matches_dj_database_url(self):
        # DATABASE_URL from compose must satisfy settings.parse_database_url.
        stack = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        url = stack["services"]["web"]["environment"]["DATABASE_URL"]
        self.assertIn("postgres://", url)
        self.assertIn("@db:5432/", url)

    def test_backup_and_restore_scripts_are_coherent(self):
        backup = BACKUP.read_text(encoding="utf-8")
        restore = RESTORE.read_text(encoding="utf-8")
        for script in (backup, restore):
            self.assertIn("set -eu", script)
        self.assertIn("pg_dump", backup)
        self.assertIn("BACKUP_DIR", backup)
        self.assertIn("pg_restore", restore)
        self.assertIn("DROP DATABASE", restore)
        self.assertIn("healthz", restore)


class CiWorkflowContractTests(SimpleTestCase):
    def test_ci_runs_the_full_gate(self):
        workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
        jobs = set(workflow["jobs"])
        self.assertIn("gate-ubuntu", jobs)
        self.assertIn("gate-windows", jobs)

        steps = []
        for job in workflow["jobs"].values():
            steps.extend(job["steps"])

        commands = " ".join(
            str(step.get("run", "")) for step in steps if isinstance(step, dict)
        )
        self.assertIn("ruff check .", commands)
        self.assertIn("manage.py check --settings=config.settings_test", commands)
        self.assertIn("makemigrations --check", commands)
        self.assertIn("manage.py test --settings=config.settings_test", commands)
        self.assertIn("check --deploy", commands)
        self.assertIn("pip-audit", commands)
        self.assertIn("tools/compile_messages.py", commands)
        # Both requirement files are installed on every runner.
        for step in steps:
            if "Install dependencies" in str(step.get("name", "")):
                run = str(step.get("run", ""))
                self.assertIn("-r requirements.txt -r requirements-dev.txt", run)

    def test_ci_python_versions_match_deployment_targets(self):
        workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
        versions = []
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                with_dict = step.get("with", {}) if isinstance(step, dict) else {}
                if with_dict.get("python-version"):
                    versions.append(with_dict["python-version"])
        self.assertIn("3.12", versions)
        self.assertIn("3.10", versions)


class DevToolingContractTests(SimpleTestCase):
    def test_babel_and_pyyaml_are_declared_dev_dependencies(self):
        text = REQS_DEV.read_text(encoding="utf-8")
        self.assertIn("babel==", text)
        self.assertIn("PyYAML==", text)

    def test_locale_is_committed_as_compiled_catalog(self):
        from django.conf import settings

        mo = Path(settings.BASE_DIR) / "locale" / "fr" / "LC_MESSAGES" / "django.mo"
        self.assertTrue(mo.exists())
        po = mo.with_suffix(".po")
        self.assertTrue(po.exists())