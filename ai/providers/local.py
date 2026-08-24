"""Offline local embeddings via fastembed/ONNX.

First-class option for a school box with no cloud access and no budget per
query: multilingual-e5-small runs on CPU for both English and French. Model
files download on first use (HuggingFace). This provider serves embeddings
only; chat generation requires a configured chat provider.
"""

from ai.providers.base import AIError, BaseProvider

DEFAULT_LOCAL_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


class LocalFastembedProvider(BaseProvider):
    name = "local"

    def __init__(self, api_key="", model=""):
        super().__init__(api_key=api_key, model=model or DEFAULT_LOCAL_EMBEDDING_MODEL)
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise AIError(
                    "fastembed is not installed; run `pip install fastembed` "
                    "for offline local embeddings."
                ) from exc
            self._model = TextEmbedding(model_name=self.model)
        return self._model

    def _embed_impl(self, texts):
        model = self._get_model()
        vectors = list(model.embed(list(texts)))
        return [[float(x) for x in vector] for vector in vectors]

    def _generate_impl(self, prompt, system=None):
        raise AIError(
            "The local provider serves embeddings only; configure a chat "
            "provider (AI_CHAT_PROVIDER) for generation."
        )