import hashlib
import logging
import math
import re
import time
from collections.abc import Callable
from typing import Protocol

from app.core.config import is_api_key_configured, settings
from fastapi import HTTPException, status
from openai import APIConnectionError, APIStatusError, OpenAI

EMBEDDING_DIMENSION = 384
FALLBACK_COOLDOWN_SECONDS = 60.0
logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> list[float]: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def index_name(self) -> str: ...


class HashingEmbeddingService:
    """Lightweight local embedding for MVP verification.

    It produces deterministic vectors without external model downloads. The
    service boundary lets us replace it with bge or DashScope embeddings later.
    """

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSION
        for token in _tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    @property
    def index_name(self) -> str:
        return "hashing_v1"


class DashScopeEmbeddingService:
    """Semantic embeddings through DashScope's OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        self.model = settings.embedding_model
        self.client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.qwen_base_url,
            timeout=settings.llm_timeout_seconds,
        )

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        try:
            for start in range(0, len(texts), settings.embedding_batch_size):
                batch = texts[start : start + settings.embedding_batch_size]
                response = self.client.embeddings.create(model=self.model, input=batch)
                ordered = sorted(response.data, key=lambda item: item.index)
                embeddings.extend(item.embedding for item in ordered)
        except APIStatusError as exc:
            logger.exception("DashScope embedding API returned status %s", exc.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Embedding API error: {exc.status_code}",
            ) from exc
        except APIConnectionError as exc:
            logger.exception("Could not connect to DashScope embedding API")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not connect to the embedding service.",
            ) from exc
        return embeddings

    @property
    def index_name(self) -> str:
        model_slug = re.sub(r"[^a-z0-9]+", "_", self.model.lower()).strip("_")
        return f"dashscope_{model_slug}"


class ResilientEmbeddingService:
    """Use the configured provider, fall back locally, and probe for recovery.

    After a failure the service serves requests with the local hashing
    provider for ``cooldown_seconds``; once the cooldown elapses the next
    request probes the primary again and switches back when it answers.
    """

    def __init__(
        self,
        primary: EmbeddingProvider,
        fallback: EmbeddingProvider | None = None,
        *,
        cooldown_seconds: float = FALLBACK_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.primary = primary
        self.fallback = fallback or HashingEmbeddingService()
        self.active: EmbeddingProvider = primary
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._fallback_since: float | None = None

    def use_fallback(self) -> None:
        if self.active is self.fallback:
            return
        logger.warning(
            "Embedding provider %s unavailable; switching to local hashing vectors",
            self.primary.index_name,
        )
        self.active = self.fallback
        self._fallback_since = self._clock()

    def _cooldown_elapsed(self) -> bool:
        if self._fallback_since is None:
            return False
        return self._clock() - self._fallback_since >= self._cooldown_seconds

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.active is self.fallback and self._cooldown_elapsed():
            recovered = self._probe_primary(texts)
            if recovered is not None:
                return recovered
        try:
            return self.active.embed_texts(texts)
        except HTTPException:
            if self.active is self.fallback:
                raise
            self.use_fallback()
            return self.active.embed_texts(texts)

    def _probe_primary(self, texts: list[str]) -> list[list[float]] | None:
        """Give the primary provider one request to prove it recovered."""
        try:
            vectors = self.primary.embed_texts(texts)
        except HTTPException:
            logger.warning(
                "Embedding primary provider %s is still unavailable; staying on local hashing",
                self.primary.index_name,
            )
            self._fallback_since = self._clock()
            return None
        logger.warning(
            "Embedding primary provider %s recovered; switching back from local hashing",
            self.primary.index_name,
        )
        self.active = self.primary
        self._fallback_since = None
        return vectors

    @property
    def index_name(self) -> str:
        return self.active.index_name


def _tokenize(text: str) -> list[str]:
    normalized = text.lower()
    words = re.findall(r"[a-z0-9_]+", normalized)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    chinese_bigrams = [
        "".join(chinese_chars[index : index + 2]) for index in range(max(0, len(chinese_chars) - 1))
    ]
    return words + chinese_chars + chinese_bigrams


has_api_key = is_api_key_configured(settings.dashscope_api_key)
if settings.embedding_provider == "dashscope" and has_api_key:
    embedding_service = ResilientEmbeddingService(DashScopeEmbeddingService())
else:
    embedding_service = ResilientEmbeddingService(HashingEmbeddingService())
