"""Groq chat provider (OpenAI-compatible endpoint).

Groq serves chat generation only - it has no embeddings API, so it is
selected through AI_CHAT_PROVIDER while embeddings keep using
AI_PROVIDER. Default model follows Groq's current production recommendation;
override with AI_CHAT_MODEL.
"""

from django.conf import settings

from ai.providers.openai_compat import OpenAICompatibleProvider

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"

    def _endpoint(self, path):
        base = (
            getattr(settings, "AI_BASE_URL", "")
            or GROQ_BASE_URL
        ).rstrip("/")
        return f"{base}/{path}"
