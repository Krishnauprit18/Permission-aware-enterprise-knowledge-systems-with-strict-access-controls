"""Local embedding contracts and offline providers."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from hashlib import sha256
from importlib import import_module
from math import sqrt
from pathlib import Path
from time import sleep
from typing import Protocol, SupportsFloat, cast


class EmbeddingError(RuntimeError):
    """Base error for bounded embedding failures."""


class EmbeddingInputError(EmbeddingError, ValueError):
    """The input violates a deterministic provider bound."""


class EmbeddingUnavailable(EmbeddingError):
    """A provider failed transiently or exceeded its timeout."""


class EmbeddingVersionMismatch(EmbeddingError):
    """A provider returned vectors incompatible with the index contract."""


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    model_name: str = "local-hash-embedding"
    model_version: str = "1"
    dimension: int = 384
    batch_size: int = 16
    max_text_chars: int = 8_000
    timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_base_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not self.model_name.strip() or not self.model_version.strip():
            raise ValueError("embedding model identity is required")
        if self.dimension < 2 or self.batch_size < 1 or self.max_text_chars < 1:
            raise ValueError("embedding bounds are invalid")
        if (
            self.timeout_seconds <= 0
            or self.max_retries < 0
            or self.retry_base_seconds < 0
        ):
            raise ValueError("embedding retry settings are invalid")


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    model_name: str
    model_version: str
    dimension: int
    vectors: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        if not self.model_name.strip() or not self.model_version.strip():
            raise ValueError("embedding batch identity is required")
        if self.dimension < 2 or any(
            len(vector) != self.dimension for vector in self.vectors
        ):
            raise ValueError("embedding vector dimension mismatch")


class EmbeddingProvider(Protocol):
    def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch: ...


_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True, slots=True)
class LocalHashEmbeddingProvider:
    """Deterministic offline baseline; no network or cloud model is used."""

    config: EmbeddingConfig = field(default_factory=EmbeddingConfig)

    def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        if len(texts) > self.config.batch_size:
            raise EmbeddingInputError("embedding batch exceeds configured size")
        vectors = tuple(self._embed_text(text) for text in texts)
        return EmbeddingBatch(
            model_name=self.config.model_name,
            model_version=self.config.model_version,
            dimension=self.config.dimension,
            vectors=vectors,
        )

    def _embed_text(self, text: str) -> tuple[float, ...]:
        if not text.strip() or len(text) > self.config.max_text_chars:
            raise EmbeddingInputError("embedding text is empty or exceeds limit")
        values = [0.0] * self.config.dimension
        tokens = _TOKEN_RE.findall(text)
        for token in tokens:
            digest = sha256(
                f"{self.config.model_version}|{token.casefold()}".encode()
            ).digest()
            index = int.from_bytes(digest[:4], "big") % self.config.dimension
            values[index] += 1.0 if digest[4] & 1 else -1.0
        norm = sqrt(sum(value * value for value in values))
        if norm == 0:
            values[0] = 1.0
            norm = 1.0
        return tuple(value / norm for value in values)


@dataclass(slots=True)
class LocalSemanticEmbeddingProvider:
    """Encode text with a locally installed FastEmbed ONNX artifact.

    The model path must already exist on the local filesystem. The adapter uses
    ``local_files_only`` and never resolves a model name or source text through
    a hosted provider. ``LocalHashEmbeddingProvider`` remains the deterministic
    test baseline; this adapter is the runtime semantic implementation.
    """

    model_path: str
    config: EmbeddingConfig
    device: str = "cpu"
    _model: object | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        path = Path(self.model_path)
        if not path.is_dir():
            raise ValueError("local embedding model path must be an existing directory")
        if self.device not in {"cpu", "cuda", "mps"}:
            raise ValueError("embedding device is unsupported")

    def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        if len(texts) > self.config.batch_size:
            raise EmbeddingInputError("embedding batch exceeds configured size")
        if any(
            not text.strip() or len(text) > self.config.max_text_chars for text in texts
        ):
            raise EmbeddingInputError("embedding text is empty or exceeds limit")
        model = self._load_model()
        encode = getattr(model, "embed", None)
        if not callable(encode):
            raise EmbeddingUnavailable("local semantic model has no embed method")
        encode_fn = cast(Callable[..., object], encode)
        try:
            encoded = encode_fn(
                list(texts),
                batch_size=len(texts),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise EmbeddingUnavailable("local semantic model failed") from exc
        rows_method = getattr(encoded, "tolist", None)
        rows_value = rows_method() if callable(rows_method) else encoded
        rows = cast(Iterable[object], rows_value)
        vectors: list[tuple[float, ...]] = []
        for row in rows:
            values = tuple(
                float(cast(SupportsFloat, value))
                for value in cast(Iterable[object], row)
            )
            vectors.append(values)
        result = EmbeddingBatch(
            model_name=self.config.model_name,
            model_version=self.config.model_version,
            dimension=self.config.dimension,
            vectors=tuple(vectors),
        )
        if len(result.vectors) != len(texts):
            raise EmbeddingVersionMismatch(
                "local semantic model returned wrong batch size"
            )
        return result

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            module = import_module("fastembed")
            model_type = getattr(module, "TextEmbedding", None)
            if not callable(model_type):
                raise EmbeddingUnavailable("fastembed runtime is unavailable")
            factory = cast(Callable[..., object], model_type)
            model = factory(
                model_name=self.config.model_name,
                cache_dir=self.model_path,
                cuda=self.device == "cuda",
                local_files_only=True,
            )
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise EmbeddingUnavailable(
                "local semantic embedding runtime or artifact is unavailable"
            ) from exc
        self._model = model
        return model


@dataclass(frozen=True, slots=True)
class ResilientEmbeddingRunner:
    """Bound batches and retry transient provider failures without logging text."""

    provider: EmbeddingProvider
    config: EmbeddingConfig
    sleeper: Callable[[float], None] = sleep

    def embed_many(self, texts: Iterable[str]) -> Iterable[EmbeddingBatch]:
        batch: list[str] = []
        for text in texts:
            batch.append(text)
            if len(batch) == self.config.batch_size:
                yield self._run(tuple(batch))
                batch.clear()
        if batch:
            yield self._run(tuple(batch))

    def _run(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        last_error: EmbeddingError | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                result = self._call_with_timeout(texts)
                if (
                    result.model_name != self.config.model_name
                    or result.model_version != self.config.model_version
                    or result.dimension != self.config.dimension
                    or len(result.vectors) != len(texts)
                ):
                    raise EmbeddingVersionMismatch(
                        "provider returned incompatible batch"
                    )
                return result
            except EmbeddingInputError:
                raise
            except EmbeddingVersionMismatch:
                raise
            except EmbeddingUnavailable as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    delay = min(
                        self.config.retry_base_seconds * (2**attempt),
                        max(self.config.retry_base_seconds, 1.0),
                    )
                    self.sleeper(delay)
                else:
                    raise
            except (EmbeddingError, OSError) as exc:
                last_error = EmbeddingUnavailable(
                    "local embedding provider unavailable"
                )
                if attempt < self.config.max_retries:
                    delay = min(
                        self.config.retry_base_seconds * (2**attempt),
                        max(self.config.retry_base_seconds, 1.0),
                    )
                    self.sleeper(delay)
                else:
                    raise last_error from exc
        raise EmbeddingUnavailable(
            "local embedding provider unavailable"
        ) from last_error

    def _call_with_timeout(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.provider.embed_batch, texts)
        try:
            return future.result(timeout=self.config.timeout_seconds)
        except FutureTimeoutError as exc:
            raise EmbeddingUnavailable("local embedding provider timed out") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
