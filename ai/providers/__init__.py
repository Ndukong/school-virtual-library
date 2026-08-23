"""Provider factory. The only place that maps settings to implementations."""

from django.conf import settings

from ai.providers.base import AIError
from ai.providers.gemini import GeminiProvider
from ai.providers.groq import DEFAULT_GROQ_MODEL, GroqProvider
from ai.providers.mock import MockAIProvider
from ai.providers.openai_compat import OpenAICompatibleProvider

_REGISTRY = {
    "mock": MockAIProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
}

# Sensible default chat models per provider; AI_CHAT_MODEL overrides.
_DEFAULT_CHAT_MODELS = {
    "mock": "mock-chat-small",
    "groq": DEFAULT_GROQ_MODEL,
    "gemini": "gemini-2.0-flash",
}


def available_providers():
    return sorted(_REGISTRY)


def _build(kind, api_key, model):
    try:
        provider_class = _REGISTRY[kind]
    except KeyError:
        raise AIError(
            f"Unknown AI provider '{kind}'. Available: {', '.join(available_providers())}."
        ) from None
    if kind != "mock" and not api_key:
        raise AIError(
            f"AI_API_KEY is required for the '{kind}' provider "
            "(set it in .env, or use AI_PROVIDER/AI_CHAT_PROVIDER=mock offline)."
        )
    return provider_class(api_key=api_key, model=model)


def get_provider(kind=None, model=None):
    """Build the configured embedding/general provider instance."""
    kind = (kind or getattr(settings, "AI_PROVIDER", "mock") or "mock").lower()
    return _build(
        kind,
        api_key=getattr(settings, "AI_API_KEY", ""),
        model=model or getattr(settings, "AI_EMBEDDING_MODEL", "mock-embed-small"),
    )


def get_chat_provider(kind=None, model=None):
    """Build the chat generation provider (Phase 5).

    Defaults to AI_CHAT_PROVIDER (recommended: groq) and a per-provider
    default model unless AI_CHAT_MODEL is set. openai_compatible has no
    universal default model - it must be configured explicitly.
    """
    kind = (kind or getattr(settings, "AI_CHAT_PROVIDER", "groq") or "groq").lower()
    if model is None:
        model = getattr(settings, "AI_CHAT_MODEL", "") or _DEFAULT_CHAT_MODELS.get(kind, "")
    if not model:
        raise AIError(
            f"AI_CHAT_MODEL must be set when using the '{kind}' provider."
        )
    return _build(
        kind,
        api_key=getattr(settings, "AI_API_KEY", ""),
        model=model,
    )
