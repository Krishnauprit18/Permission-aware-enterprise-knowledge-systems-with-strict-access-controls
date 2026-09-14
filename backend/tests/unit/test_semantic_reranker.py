"""Unit regressions for the configured local semantic cross-encoder adapter."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest

from knowledge_system.adapters.models.reranker import (
    FastEmbedCrossEncoderReranker,
    SemanticRerankerConfig,
)
from knowledge_system.application.evidence import RerankerUnavailable
from knowledge_system.domain.contracts import (
    AuthorizedChunk,
    AuthorizedObjectId,
    EvidenceId,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]


@dataclass
class FakeCrossEncoder:
    scores: tuple[float, ...]
    calls: list[tuple[str, tuple[str, ...], int]]

    def rerank(
        self, query: str, documents: Iterable[str], *, batch_size: int
    ) -> tuple[float, ...]:
        values: tuple[str, ...] = tuple(documents)
        self.calls.append((query, values, batch_size))
        return self.scores


def _chunks() -> tuple[AuthorizedChunk, ...]:
    return (
        AuthorizedChunk(
            object_id=AuthorizedObjectId("resource:approved"),
            evidence_id=EvidenceId("evidence-approved"),
            text="The release board approved the September 24 rollout date.",
            tenant_id="northstar",
        ),
        AuthorizedChunk(
            object_id=AuthorizedObjectId("resource:unrelated"),
            evidence_id=EvidenceId("evidence-unrelated"),
            text="The cafeteria menu includes lentil soup on Wednesday.",
            tenant_id="northstar",
        ),
    )


def test_semantic_adapter_ranks_supplied_authorized_chunks_only(tmp_path: Path) -> None:
    config = SemanticRerankerConfig(
        cache_dir=tmp_path,
        batch_size=2,
    )
    fake = FakeCrossEncoder(scores=(8.5, -4.0), calls=[])
    received: list[SemanticRerankerConfig] = []

    def factory(value: SemanticRerankerConfig) -> FakeCrossEncoder:
        received.append(value)
        return fake

    reranker = FastEmbedCrossEncoderReranker(
        config,
        encoder_factory=factory,
    )

    scores = reranker.rerank(
        "What is the approved rollout date?", _chunks(), limit=2, timeout_ms=1_000
    )

    assert received == [config]
    assert fake.calls == [
        (
            "What is the approved rollout date?",
            tuple(chunk.text for chunk in _chunks()),
            2,
        )
    ]
    assert [score.evidence_id for score in scores] == [
        EvidenceId("evidence-approved"),
        EvidenceId("evidence-unrelated"),
    ]
    assert reranker.reranker_version.endswith(
        "@a09144355adeed5f58c8ed011d209bf8ee5a1fec"
    )


def test_semantic_adapter_fails_closed_when_the_local_artifact_is_unavailable(
    tmp_path: Path,
) -> None:
    config = SemanticRerankerConfig(cache_dir=tmp_path)

    reranker = FastEmbedCrossEncoderReranker(
        config,
        encoder_factory=lambda _config: (_ for _ in ()).throw(OSError("missing")),
    )

    with pytest.raises(RerankerUnavailable, match="semantic reranker unavailable"):
        reranker.rerank("approved date", _chunks(), limit=2, timeout_ms=1_000)


def test_semantic_adapter_rejects_network_enabled_model_loading(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not fetch"):
        SemanticRerankerConfig(cache_dir=tmp_path, local_files_only=False)
