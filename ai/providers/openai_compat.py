"""OpenAI-compatible provider (NVIDIA NIM, routers, vLLM, OpenAI itself).

Configure via AI_BASE_URL, e.g.
    NVIDIA NIM:   https://integrate.api.nvidia.com/v1
Any endpoint exposing POST {base}/embeddings and {base}/chat/completions works.
"""

import json

from django.conf import settings

from ai.providers.base import AIError, BaseProvider, GenerateResult


class OpenAICompatibleProvider(BaseProvider):
    name = "openai_compatible"

    def _headers(self):
        if not self.api_key:
            raise AIError("AI_API_KEY is not configured.")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _endpoint(self, path):
        base = getattr(settings, "AI_BASE_URL", "").rstrip("/")
        if not base:
            raise AIError("AI_BASE_URL is not configured for openai_compatible provider.")
        return f"{base}/{path}"

    def _embed_impl(self, texts):
        payload = {"model": self.model, "input": list(texts)}
        data = self._post_json(
            self._endpoint("embeddings"), payload, self._headers(), "EMBED", len(texts)
        )
        rows = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [row.get("embedding") for row in rows]
        if len(vectors) != len(texts) or any(not v for v in vectors):
            raise AIError("Embedding response did not contain all requested vectors.")
        return vectors

    def _generate_impl(self, prompt, system=None):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model, "messages": messages}
        data = self._post_json(
            self._endpoint("chat/completions"), payload, self._headers(), "GENERATE"
        )
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return GenerateResult(
            text=message.get("content", ""),
            model=data.get("model", self.model),
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
        )
