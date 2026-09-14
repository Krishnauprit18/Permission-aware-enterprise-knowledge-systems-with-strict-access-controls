"""Opt-in proof that the pinned local ONNX cross-encoder works without network."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from knowledge_system.adapters.models.reranker import (
    FastEmbedCrossEncoderReranker,
    SemanticRerankerConfig,
)
from knowledge_system.domain.contracts import (
    AuthorizedChunk,
    AuthorizedObjectId,
    EvidenceId,
)

pytestmark = [pytest.mark.integration, pytest.mark.security]


def test_live_local_cross_encoder_reranks_without_network() -> None:
    if os.environ.get("P13_SEMANTIC_RERANKER_LIVE") != "1":
        pytest.skip("set P13_SEMANTIC_RERANKER_LIVE=1 for local semantic evidence")
    model_path = Path(os.environ.get("SEMANTIC_RERANKER_MODEL_PATH", ""))
    if not model_path.is_dir():
        pytest.skip("SEMANTIC_RERANKER_MODEL_PATH must be a local model cache")
    reranker = FastEmbedCrossEncoderReranker(
        SemanticRerankerConfig(cache_dir=model_path, batch_size=2)
    )
    scores = reranker.rerank(
        "What is the approved Acme rollout date?",
        (
            AuthorizedChunk(
                object_id=AuthorizedObjectId("resource:approved"),
                evidence_id=EvidenceId("evidence-approved"),
                text="The release board approved Acme rollout for September 24.",
                tenant_id="northstar",
            ),
            AuthorizedChunk(
                object_id=AuthorizedObjectId("resource:menu"),
                evidence_id=EvidenceId("evidence-menu"),
                text="The cafeteria menu contains lentil soup and flatbread.",
                tenant_id="northstar",
            ),
        ),
        limit=2,
        timeout_ms=5_000,
    )

    assert [score.evidence_id for score in scores] == [
        EvidenceId("evidence-approved"),
        EvidenceId("evidence-menu"),
    ]
