"""Export a single user's personal data (data-subject access request).

    python manage.py export_user_data offstu --out export.json

Produces a JSON snapshot of that user's AI history, practice attempts and
account metadata. Existing files are never overwritten: the command fails
unless --out points to a fresh path.
"""

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ai.models import AIGeneration, AIInteraction
from learning.models import AttemptResponse, PracticeAttempt


class Command(BaseCommand):
    help = "Export one user's personal data to a JSON file (no overwrite)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--out", required=True, help="Path of the JSON file to write.")

    def _export(self, user):
        interactions = AIInteraction.objects.filter(user=user).order_by("created_at")
        generations = AIGeneration.objects.filter(user=user).order_by("created_at")
        attempts = PracticeAttempt.objects.filter(student=user).order_by("created_at")
        attempt_data = []
        for attempt in attempts:
            responses = AttemptResponse.objects.filter(attempt=attempt).order_by("position")
            attempt_data.append({
                "source": attempt.get_source_type_display(),
                "subject": attempt.subject.name if attempt.subject else None,
                "status": attempt.get_status_display(),
                "earned_marks": attempt.earned_marks,
                "possible_marks": attempt.possible_marks,
                "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
                "responses": [
                    {
                        "question": response.question.body[:4000],
                        "given_answer": response.given_answer[:4000] or None,
                        "is_correct": response.is_correct,
                        "awarded_marks": response.awarded_marks,
                    }
                    for response in responses
                ],
            })
        return {
            "exported_at": timezone.now().isoformat(),
            "user": {
                "username": user.username,
                "full_name": user.get_full_name(),
                "role": user.get_role_display(),
                "language": user.language,
                "is_active": user.is_active,
            },
            "school": user.school.name if user.school else None,
            "ai_interactions": [
                {
                    "scope": interaction.get_scope_display(),
                    "question": interaction.question,
                    "answer": interaction.answer,
                    "model": interaction.model,
                    "used_provider": interaction.used_provider,
                    "prompt_version": interaction.prompt_version,
                    "created_at": interaction.created_at.isoformat()
                    if interaction.created_at
                    else None,
                }
                for interaction in interactions
            ],
            "ai_generations": [
                {
                    "kind": generation.get_kind_display(),
                    "scope": generation.get_scope_display(),
                    "topic": generation.topic,
                    "content": generation.content,
                    "model": generation.model,
                    "created_at": generation.created_at.isoformat()
                    if generation.created_at
                    else None,
                }
                for generation in generations
            ],
            "practice_attempts": attempt_data,
        }

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.select_related("school").filter(
            username=options["username"]
        ).first()
        if user is None:
            raise CommandError(f"No user with username '{options['username']}'.")

        from pathlib import Path

        out_path = Path(options["out"]).resolve()
        if out_path.exists():
            raise CommandError(f"Refusing to overwrite an existing file: {out_path}")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        payload = self._export(user)
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"Exported {out_path}"))