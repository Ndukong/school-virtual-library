"""Provider factory. The only place that maps settings to implementations."""

from django.conf import settings

from ai.providers.base import AIError, BaseProvider
from ai.providers.gemini import GeminiProvider
from ai.providers.mock import MockAIProvider
from ai.providers.openai_compat import OpenAICompatibleProvider

_REGISTRY = {
    "mock": MockAIProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "gemini": GeminiProvider,
}


def available_providers():
    return sorted(_REGISTRY)


def get_provider(kind=None, model=None):
    """Build the configured provider instance.

    kind/model default to AI_PROVIDER / AI_EMBEDDING_MODEL from settings;
    callers may override (e.g. chat generation passes AI_CHAT_MODEL).
    """
    kind = (kind or getattr(settings, "AI_PROVIDER", "mock") or "mock").lower()
    try:
        provider_class = _REGISTRY[kind]
    except KeyError:
        raise AIError(
            f"Unknown AI_PROVIDER '{kind}'. Available: {', '.join(available_providers())}."
        ) from None
    return provider_class(
        api_key=getattr(settings, "AI_API_KEY", ""),
        model=model or getattr(settings, "AI_EMBEDDING_MODEL", "mock-embed-small"),
    )
