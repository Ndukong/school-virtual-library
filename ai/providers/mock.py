"""Offline mock provider: deterministic hash-based vectors.

Vectors are stable for a given (model, text) pair, so tests can assert
re-use and re-embedding behaviour without any network. Similarity between
different texts is arbitrary by design; only determinism is guaranteed.
"""

import hashlib

from ai.providers.base import BaseProvider, GenerateResult

MOCK_DIMENSIONS = 16


class MockAIProvider(BaseProvider):
    name = "mock"

    def _vector(self, text):
        digest = hashlib.sha256(f"{self.model}:{text}".encode()).digest()
        vector = []
        for i in range(MOCK_DIMENSIONS):
            byte = digest[i % len(digest)]
            vector.append(((byte / 255.0) * 2.0) - 1.0)
        return vector

    def _embed_impl(self, texts):
        return [self._vector(t) for t in texts]

    def _generate_impl(self, prompt, system=None):
        return GenerateResult(
            text="[mock] " + prompt[:100],
            model=self.model,
            tokens_in=len(prompt.split()),
            tokens_out=3,
        )
