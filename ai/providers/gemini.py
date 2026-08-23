"""Google Gemini provider via the Generative Language REST API.

Embeddings use models/{model}:batchEmbedContents; generation uses
models/{model}:generateContent. The API key is passed as a query parameter
per Google's documented scheme for server-side calls.
"""

import json

from ai.providers.base import AIError, BaseProvider, GenerateResult

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(BaseProvider):
    name = "gemini"

    def _headers(self):
        if not self.api_key:
            raise AIError("AI_API_KEY is not configured.")
        return {"Content-Type": "application/json"}

    def _post(self, path, payload, kind, input_items=1):
        url = f"{GEMINI_BASE}/{path}?key={self.api_key}"
        return self._post_json(url, payload, self._headers(), kind, input_items)

    def _embed_impl(self, texts):
        requests_list = [
            {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}}
            for t in texts
        ]
        data = self._post(
            f"models/{self.model}:batchEmbedContents",
            {"requests": requests_list},
            "EMBED",
            len(texts),
        )
        vectors = [
            entry.get("values") for entry in data.get("embeddings", [])
        ]
        if len(vectors) != len(texts) or any(not v for v in vectors):
            raise AIError("Embedding response did not contain all requested vectors.")
        return vectors

    def _generate_impl(self, prompt, system=None):
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        payload = {"contents": contents}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        data = self._post(f"models/{self.model}:generateContent", payload, "GENERATE")
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise AIError(f"Unexpected Gemini response shape: {json.dumps(data)[:300]}") from exc
        usage = data.get("usageMetadata") or {}
        return GenerateResult(
            text=text,
            model=self.model,
            tokens_in=usage.get("promptTokenCount"),
            tokens_out=usage.get("candidatesTokenCount"),
        )
