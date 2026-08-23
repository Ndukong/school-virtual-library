"""AI usage tracking (AGENTS.md sections 14/28)."""

from django.db import models


class AIRequestLog(models.Model):
    """One row per outbound AI call, successful or not."""

    class Kind(models.TextChoices):
        EMBED = "EMBED", "Embedding"
        GENERATE = "GENERATE", "Generation"

    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    ok = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    input_items = models.PositiveIntegerField(default=1)
    tokens_in = models.PositiveIntegerField(null=True, blank=True)
    tokens_out = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "model", "kind"]),
        ]

    def __str__(self):
        status = "ok" if self.ok else "error"
        return f"{self.provider}/{self.model} {self.kind} [{status}]"
