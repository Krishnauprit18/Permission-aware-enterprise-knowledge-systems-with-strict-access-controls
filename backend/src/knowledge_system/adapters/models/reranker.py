"""Cache-only local semantic cross-encoder adapter for authorized evidence."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Protocol

from knowledge_system.application.evidence import RerankerTimeout, RerankerUnavailable
from knowledge_system.application.ports.knowledge import Reranker
from knowledge_system.domain.contracts import AuthorizedChunk
from knowledge_system.domain.evidence import RerankScore


class CrossEncoder(Protocol):
    """Minimal local-model surface retained behind the adapter."""

    def rerank(
        self, query: str, documents: Iterable[str], *, batch_size: int
    ) -> Iterable[float]: ...


CrossEncoderFactory = Callable[["SemanticRerankerConfig"], CrossEncoder]


@dataclass(frozen=True, slots=True)
class SemanticRerankerConfig:
    """Pinned local artifact settings; network loading is intentionally disabled."""

    model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    model_version: str = (
        "a09144355adeed5f58c8ed011d209bf8ee5a1fec"  # pragma: allowlist secret
    )
    cache_dir: Path = Path("/var/lib/knowledge-system/models")
    batch_size: int = 16
    threads: int = 1
    local_files_only: bool = True

    def __post_init__(self) -> None:
        if not self.model_name.strip() or not self.model_version.strip():
            raise ValueError("semantic reranker model identity is required")
        if not self.cache_dir.is_absolute():
            raise ValueError("semantic reranker cache directory must be absolute")
        if not 1 <= self.batch_size <= 64 or not 1 <= self.threads <= 8:
            raise ValueError("semantic reranker resource bounds are invalid")
        if not self.local_files_only:
            raise ValueError("semantic reranker must not fetch models at runtime")


class FastEmbedCrossEncoderReranker(Reranker):
    """Score only supplied, already-authorized text with a local ONNX cross-encoder."""

    def __init__(
        self,
        config: SemanticRerankerConfig,
        *,
        encoder_factory: CrossEncoderFactory | None = None,
    ) -> None:
        self._config = config
        self._encoder_factory = encoder_factory or _fastembed_cross_encoder
        self._encoder: CrossEncoder | None = None

    @property
    def reranker_version(self) -> str:
        return f"fastembed-cross-encoder:{self._config.model_name}@{self._config.model_version}"

    def rerank(
        self,
        query: str,
        chunks: Sequence[AuthorizedChunk],
        *,
        limit: int,
        timeout_ms: int,
    ) -> Sequence[RerankScore]:
        if not query.strip() or not 1 <= limit <= len(chunks) or timeout_ms < 1:
            raise ValueError("semantic reranker input bounds are invalid")
        if any(not chunk.text.strip() for chunk in chunks):
            raise ValueError("semantic reranker chunks must be non-empty")
        started = monotonic()
        try:
            encoder = self._encoder or self._encoder_factory(self._config)
            self._encoder = encoder
            scores = tuple(
                float(score)
                for score in encoder.rerank(
                    query,
                    (chunk.text for chunk in chunks),
                    batch_size=self._config.batch_size,
                )
            )
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise RerankerUnavailable("local semantic reranker unavailable") from exc
        elapsed_ms = (monotonic() - started) * 1_000
        if elapsed_ms > timeout_ms:
            raise RerankerTimeout("local semantic reranker timed out")
        if len(scores) != len(chunks):
            raise RerankerUnavailable(
                "local semantic reranker returned an invalid score count"
            )
        ranked = sorted(
            zip(scores, chunks, strict=True),
            key=lambda value: (-value[0], str(value[1].evidence_id)),
        )
        return tuple(
            RerankScore(evidence_id=chunk.evidence_id, score=score)
            for score, chunk in ranked[:limit]
        )


def _fastembed_cross_encoder(config: SemanticRerankerConfig) -> CrossEncoder:
    """Instantiate FastEmbed lazily so deterministic tests need no model artifact."""

    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(
        model_name=config.model_name,
        cache_dir=str(config.cache_dir),
        threads=config.threads,
        cuda=False,
        local_files_only=config.local_files_only,
    )
