"""AI provider abstraction (AGENTS.md section 13).

The rest of the application calls get_provider() and never imports provider
SDKs or HTTP details. All implementations share retry/timeout/logging
behaviour defined here.
"""

import abc
import json
import time
import urllib.error
import urllib.request

from django.conf import settings

from ai.models import AIRequestLog


class AIError(Exception):
    """Raised when a provider call ultimately fails after retries."""


class GenerateResult:
    def __init__(self, text, model, tokens_in=None, tokens_out=None):
        self.text = text
        self.model = model
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out


class BaseProvider(abc.ABC):
    name = "base"

    def __init__(self, api_key="", model=""):
        self.api_key = api_key
        self.model = model

    @abc.abstractmethod
    def _embed_impl(self, texts):
        """Return one embedding vector per input text."""

    @abc.abstractmethod
    def _generate_impl(self, prompt, system=None):
        """Return a GenerateResult for a single prompt."""

    def embed(self, texts):
        """Logged wrapper around _embed_impl."""
        started = time.monotonic()
        try:
            vectors = self._embed_impl(texts)
        except AIError:
            raise  # HTTP layer already logged each failed attempt
        except Exception as exc:  # noqa: BLE001
            self._log("EMBED", False, (time.monotonic() - started) * 1000,
                      input_items=len(texts), error=exc)
            raise
        self._log("EMBED", True, (time.monotonic() - started) * 1000, input_items=len(texts))
        return vectors

    def generate(self, prompt, system=None):
        """Logged wrapper around _generate_impl."""
        started = time.monotonic()
        try:
            result = self._generate_impl(prompt, system)
        except AIError:
            raise  # HTTP layer already logged each failed attempt
        except Exception as exc:  # noqa: BLE001
            self._log("GENERATE", False, (time.monotonic() - started) * 1000,
                      input_items=1, error=exc)
            raise
        self._log(
            "GENERATE", True, (time.monotonic() - started) * 1000,
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
        )
        return result

    # -- shared plumbing -------------------------------------------------

    def _log(self, kind, ok, latency_ms, input_items=1, error="", tokens_in=None, tokens_out=None):
        AIRequestLog.objects.create(
            provider=self.name,
            model=self.model,
            kind=kind,
            ok=ok,
            error=str(error)[:5000],
            input_items=input_items,
            latency_ms=int(latency_ms),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def _post_json(self, url, payload, headers, kind, input_items=1):
        """POST JSON with timeout + retries; logs every FAILED attempt."""
        attempts = max(1, int(getattr(settings, "AI_MAX_RETRIES", 2)) + 1)
        timeout = getattr(settings, "AI_TIMEOUT_SECONDS", 30)
        last_error = ""
        for attempt in range(1, attempts + 1):
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            started = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                return data
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:500]
                last_error = f"HTTP {exc.code}: {detail}"
            except Exception as exc:  # noqa: BLE001 - network layer is unpredictable
                last_error = f"{type(exc).__name__}: {exc}"
            self._log(
                kind, False, (time.monotonic() - started) * 1000, input_items, error=last_error
            )
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 8))
        raise AIError(f"{self.name} {kind} failed after {attempts} attempt(s): {last_error}")
