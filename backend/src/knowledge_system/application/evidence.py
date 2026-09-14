"""Bounded local reranking and deterministic evidence resolution for P13."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC
from hashlib import sha256
from time import monotonic

from knowledge_system.application.content import normalize_untrusted_text
from knowledge_system.application.ports.authorization import (
    AuthorizationPort,
    AuthorizationUnavailable,
)
from knowledge_system.application.ports.knowledge import (
    EvidenceContentStore,
    EvidenceResolver,
    Reranker,
)
from knowledge_system.domain.contracts import (
    AuthorizationOutcome,
    AuthorizedChunk,
    EvidenceId,
    PrincipalContext,
)
from knowledge_system.domain.evidence import (
    EvidenceAnnotation,
    EvidenceConflict,
    EvidenceDecisionStatus,
    EvidenceFreshness,
    EvidenceMaterial,
    EvidencePacket,
    EvidencePolicyMetadata,
    EvidenceRankDiagnostics,
    EvidenceResolution,
    EvidenceResolutionError,
    EvidenceResolutionInput,
    EvidenceResolutionTrace,
    EvidenceSourceGroup,
    RerankScore,
    policy_priority,
    stable_evidence_id,
)
from knowledge_system.domain.persistence import Classification
from knowledge_system.domain.retrieval import RetrievalCandidate, RetrievalResult


class RerankerUnavailable(RuntimeError):
    """The local reranker failed without returning a safe ranking."""


class RerankerTimeout(RerankerUnavailable):
    """A bounded reranking operation exceeded its configured local budget."""


class EvidenceAuthorizationError(RuntimeError):
    """Current authorization could not be confirmed before protected text access."""


class EvidenceContentUnavailable(RuntimeError):
    """Authorized evidence content could not be loaded safely."""


_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


@dataclass(frozen=True, slots=True)
class EvidenceResolutionLimits:
    """Independent resource bounds for P13's local in-process work."""

    max_input_candidates: int = 50
    max_rerank_candidates: int = 20
    max_evidence_text_chars: int = 12_000
    reranker_timeout_ms: int = 250
    overlap_threshold: float = 0.85

    def __post_init__(self) -> None:
        if not 1 <= self.max_rerank_candidates <= self.max_input_candidates <= 50:
            raise ValueError("candidate limits are invalid")
        if not 1 <= self.max_evidence_text_chars <= 20_000:
            raise ValueError("evidence text limit is invalid")
        if not 1 <= self.reranker_timeout_ms <= 5_000:
            raise ValueError("reranker timeout is invalid")
        if not 0.0 < self.overlap_threshold <= 1.0:
            raise ValueError("overlap threshold is invalid")


@dataclass(frozen=True, slots=True)
class LocalPairwiseReranker(Reranker):
    """Deterministic local query-document pair scorer; it never retrieves data."""

    reranker_version: str = "local-pairwise-lexical-v1"

    def rerank(
        self,
        query: str,
        chunks: Sequence[AuthorizedChunk],
        *,
        limit: int,
        timeout_ms: int,
    ) -> Sequence[RerankScore]:
        if not query.strip() or not 1 <= limit <= len(chunks) or timeout_ms < 1:
            raise ValueError("reranker input bounds are invalid")
        started = monotonic()
        query_terms = Counter(_TOKEN_RE.findall(query.lower()))
        scored: list[tuple[float, str, EvidenceId]] = []
        for chunk in chunks:
            if (monotonic() - started) * 1_000 > timeout_ms:
                raise RerankerTimeout("local reranker timed out")
            document_terms = Counter(_TOKEN_RE.findall(chunk.text.lower()))
            overlap = sum(
                min(count, document_terms[term]) for term, count in query_terms.items()
            )
            coverage = sum(1 for term in query_terms if term in document_terms) / max(
                len(query_terms), 1
            )
            phrase_bonus = 1.0 if query.lower().strip() in chunk.text.lower() else 0.0
            score = coverage * 100.0 + float(overlap) * 5.0 + phrase_bonus
            scored.append((score, str(chunk.evidence_id), chunk.evidence_id))
        scored.sort(key=lambda value: (-value[0], value[1]))
        return tuple(
            RerankScore(evidence_id=evidence_id, score=score)
            for score, _stable_id, evidence_id in scored[:limit]
        )


@dataclass(frozen=True, slots=True)
class DeterministicEvidenceResolver:
    """Resolve policy metadata without interpreting or averaging source text."""

    resolver_version: str = "evidence-policy-v1"
    overlap_threshold: float = 0.85

    def resolve(
        self,
        inputs: Sequence[EvidenceResolutionInput],
        *,
        correlation_id: str,
        authorization_fingerprint: str,
        reranker_version: str,
        input_candidate_count: int,
        reauthorized_candidate_count: int,
        authorization_drop_count: int,
    ) -> EvidenceResolution:
        packets: list[EvidencePacket] = []
        duplicate_count = 0
        seen_text: set[tuple[str, str]] = set()
        prior_by_document: dict[tuple[str, str], list[EvidencePacket]] = defaultdict(
            list
        )

        for item in inputs:
            candidate = item.material.candidate
            text_key = (candidate.document_version_id, item.sanitized_text)
            if text_key in seen_text or self._overlaps_adjacent(
                item,
                prior_by_document[
                    (candidate.document_id, candidate.document_version_id)
                ],
            ):
                duplicate_count += 1
                continue
            seen_text.add(text_key)
            classification = self._classification(candidate.classification)
            policy = item.material.policy
            annotations = self._base_annotations(policy)
            reasons = self._base_reasons(item, policy)
            source_url = candidate.provenance.get("source_url") or None
            packet = EvidencePacket(
                evidence_id=item.evidence_id,
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                document_version_id=candidate.document_version_id,
                sanitized_text=item.sanitized_text,
                source_type=candidate.source_type,
                source_locator=candidate.citation_locators,
                source_url=source_url,
                updated_at=candidate.updated_at.astimezone(UTC),
                effective_at=policy.effective_at,
                authority_level=policy.authority_level,
                freshness=policy.freshness,
                decision_status=policy.decision_status,
                classification=classification,
                external_shareable=(
                    candidate.external_shareable
                    and classification
                    in {Classification.PUBLIC, Classification.CUSTOMER_SHAREABLE}
                ),
                conflict_group=policy.conflict_group,
                supersedes_document_ids=policy.supersedes_document_ids,
                superseded_by_document_ids=policy.superseded_by_document_ids,
                annotations=tuple(annotations),
                authorization_fingerprint=authorization_fingerprint,
                diagnostics=EvidenceRankDiagnostics(
                    retrieval_rank=item.retrieval_rank,
                    rerank_rank=item.rerank_rank,
                    rerank_score=item.rerank_score,
                    fallback_used=item.fallback_used,
                    reasons=tuple(reasons),
                ),
            )
            packets.append(packet)
            prior_by_document[
                (candidate.document_id, candidate.document_version_id)
            ].append(packet)

        packets = self._annotate_conflicts_and_lineage(packets)
        source_groups = self._source_groups(packets)
        conflicts = self._conflicts(packets)
        most_relevant = packets[0].evidence_id if packets else None
        most_authoritative = (
            max(packets, key=policy_priority).evidence_id if packets else None
        )
        return EvidenceResolution(
            packets=tuple(packets),
            source_groups=source_groups,
            conflicts=conflicts,
            most_relevant_evidence_id=most_relevant,
            most_authoritative_evidence_id=most_authoritative,
            trace=EvidenceResolutionTrace(
                correlation_id=correlation_id,
                authorization_fingerprint=authorization_fingerprint,
                reranker_version=reranker_version,
                input_candidate_count=input_candidate_count,
                reauthorized_candidate_count=reauthorized_candidate_count,
                loaded_material_count=len(inputs),
                duplicate_count=duplicate_count,
                authorization_drop_count=authorization_drop_count,
                fallback_used=any(item.fallback_used for item in inputs),
            ),
        )

    def _overlaps_adjacent(
        self,
        item: EvidenceResolutionInput,
        existing: Sequence[EvidencePacket],
    ) -> bool:
        ordinal = self._ordinal(item.material.candidate)
        if ordinal is None:
            return False
        terms = set(_TOKEN_RE.findall(item.sanitized_text.lower()))
        if not terms:
            return False
        for packet in existing:
            existing_ordinal = self._ordinal_from_packet(packet)
            if existing_ordinal is None or abs(existing_ordinal - ordinal) > 1:
                continue
            other_terms = set(_TOKEN_RE.findall(packet.sanitized_text.lower()))
            union = terms | other_terms
            if (
                union
                and len(terms & other_terms) / len(union) >= self.overlap_threshold
            ):
                return True
        return False

    @staticmethod
    def _ordinal(candidate: RetrievalCandidate) -> int | None:
        raw = candidate.provenance.get("ordinal")
        try:
            value = int(raw) if raw is not None else -1
        except ValueError:
            return None
        return value if value >= 0 else None

    @staticmethod
    def _ordinal_from_packet(packet: EvidencePacket) -> int | None:
        for reason in packet.diagnostics.reasons:
            if reason.startswith("ordinal="):
                try:
                    return int(reason.removeprefix("ordinal="))
                except ValueError:
                    return None
        return None

    @staticmethod
    def _classification(value: str) -> Classification:
        try:
            return Classification(value)
        except ValueError as exc:
            raise EvidenceResolutionError("evidence classification is invalid") from exc

    @staticmethod
    def _base_annotations(
        metadata: EvidencePolicyMetadata,
    ) -> list[EvidenceAnnotation]:
        annotations: list[EvidenceAnnotation] = []
        if metadata.freshness is EvidenceFreshness.CURRENT:
            annotations.append(EvidenceAnnotation.CURRENT)
        elif metadata.freshness is EvidenceFreshness.STALE:
            annotations.append(EvidenceAnnotation.STALE)
        elif metadata.freshness is EvidenceFreshness.SUPERSEDED:
            annotations.append(EvidenceAnnotation.SUPERSEDED)
        if metadata.supersedes_document_ids:
            annotations.append(EvidenceAnnotation.SUPERSEDES)
        if metadata.superseded_by_document_ids:
            annotations.append(EvidenceAnnotation.SUPERSEDED)
        status_annotations = {
            EvidenceDecisionStatus.TENTATIVE: EvidenceAnnotation.TENTATIVE,
            EvidenceDecisionStatus.APPROVED: EvidenceAnnotation.APPROVED,
            EvidenceDecisionStatus.COMMITTED: EvidenceAnnotation.COMMITTED,
        }
        status_annotation = status_annotations.get(metadata.decision_status)
        if status_annotation is not None:
            annotations.append(status_annotation)
        return annotations

    def _base_reasons(
        self, item: EvidenceResolutionInput, metadata: EvidencePolicyMetadata
    ) -> list[str]:
        reasons = [
            "rerank-fallback" if item.fallback_used else "local-pairwise-rerank",
            f"freshness={metadata.freshness.value.lower()}",
            f"decision-status={metadata.decision_status.value.lower()}",
            f"authority-level={metadata.authority_level}",
        ]
        ordinal = self._ordinal(item.material.candidate)
        if ordinal is not None:
            reasons.append(f"ordinal={ordinal}")
        return reasons

    @staticmethod
    def _append_annotation(
        packet: EvidencePacket, annotation: EvidenceAnnotation, reason: str
    ) -> EvidencePacket:
        annotations = packet.annotations
        if annotation not in annotations:
            annotations = (*annotations, annotation)
        reasons = packet.diagnostics.reasons
        if reason not in reasons:
            reasons = (*reasons, reason)
        return replace(
            packet,
            annotations=annotations,
            diagnostics=replace(packet.diagnostics, reasons=reasons),
        )

    def _annotate_conflicts_and_lineage(
        self, packets: list[EvidencePacket]
    ) -> list[EvidencePacket]:
        result = list(packets)
        by_document = {packet.document_id: packet for packet in result}
        for index, packet in enumerate(result):
            if packet.superseded_by_document_ids or any(
                packet.document_id in other.supersedes_document_ids for other in result
            ):
                result[index] = self._append_annotation(
                    result[index], EvidenceAnnotation.SUPERSEDED, "superseded-lineage"
                )
            if any(
                document_id in by_document
                for document_id in packet.supersedes_document_ids
            ):
                result[index] = self._append_annotation(
                    result[index], EvidenceAnnotation.SUPERSEDES, "supersedes-lineage"
                )
        by_group: dict[str, list[int]] = defaultdict(list)
        for index, packet in enumerate(result):
            if packet.conflict_group is not None:
                by_group[packet.conflict_group].append(index)
        for group, indexes in by_group.items():
            if len(indexes) < 2:
                continue
            best = max((result[index] for index in indexes), key=policy_priority)
            for index in indexes:
                result[index] = self._append_annotation(
                    result[index],
                    EvidenceAnnotation.CONFLICTING,
                    f"conflict-group={group}",
                )
                if result[index].evidence_id != best.evidence_id:
                    result[index] = self._append_annotation(
                        result[index],
                        EvidenceAnnotation.LOWER_AUTHORITY,
                        "lower-authority-in-conflict",
                    )
        return result

    @staticmethod
    def _source_groups(
        packets: Sequence[EvidencePacket],
    ) -> tuple[EvidenceSourceGroup, ...]:
        grouped: dict[tuple[str, str], list[EvidenceId]] = defaultdict(list)
        for packet in packets:
            grouped[(packet.document_id, packet.document_version_id)].append(
                packet.evidence_id
            )
        return tuple(
            EvidenceSourceGroup(document_id, version_id, tuple(evidence_ids))
            for (document_id, version_id), evidence_ids in sorted(grouped.items())
        )

    @staticmethod
    def _conflicts(packets: Sequence[EvidencePacket]) -> tuple[EvidenceConflict, ...]:
        grouped: dict[str, list[EvidencePacket]] = defaultdict(list)
        for packet in packets:
            if packet.conflict_group is not None:
                grouped[packet.conflict_group].append(packet)
        conflicts: list[EvidenceConflict] = []
        for group, values in sorted(grouped.items()):
            if len(values) < 2:
                continue
            most_authoritative = max(values, key=policy_priority).evidence_id
            conflicts.append(
                EvidenceConflict(
                    conflict_group=group,
                    evidence_ids=tuple(value.evidence_id for value in values),
                    most_authoritative_evidence_id=most_authoritative,
                )
            )
        return tuple(conflicts)


@dataclass(frozen=True, slots=True)
class EvidenceResolutionService:
    """Reauthorize, load, rerank, and resolve P12 candidates without retrieval."""

    authorization: AuthorizationPort
    content_store: EvidenceContentStore
    reranker: Reranker
    resolver: EvidenceResolver = field(default_factory=DeterministicEvidenceResolver)
    limits: EvidenceResolutionLimits = field(default_factory=EvidenceResolutionLimits)

    def resolve(
        self,
        principal: PrincipalContext,
        question: str,
        retrieval: RetrievalResult,
    ) -> EvidenceResolution:
        if not 1 <= len(question.strip()) <= 2_000:
            raise ValueError("evidence query length is outside the allowed bound")
        selected = retrieval.candidates[: self.limits.max_input_candidates]
        reauthorized, authorization_drops = self._reauthorize(principal, selected)
        materials = self._load_materials(reauthorized)
        prepared = self._prepare(materials, reauthorized)
        ranked, fallback_used = self._rerank(question, prepared)
        inputs = self._resolution_inputs(ranked, fallback_used)
        return self.resolver.resolve(
            inputs,
            correlation_id=principal.correlation_id,
            authorization_fingerprint=self._current_authorization_fingerprint(
                reauthorized,
                fallback=retrieval.trace.authorization_fingerprint,
            ),
            reranker_version=self.reranker.reranker_version,
            input_candidate_count=len(selected),
            reauthorized_candidate_count=len(reauthorized),
            authorization_drop_count=authorization_drops,
        )

    @staticmethod
    def _current_authorization_fingerprint(
        candidates: Sequence[RetrievalCandidate], *, fallback: str
    ) -> str:
        """Bind P13 packets to the current per-resource reauthorization pass."""

        if not candidates:
            return fallback
        fingerprints = tuple(
            sorted(
                {
                    candidate.authorization.decision_fingerprint
                    for candidate in candidates
                }
            )
        )
        if not all(fingerprint.strip() for fingerprint in fingerprints):
            raise EvidenceAuthorizationError("authorized evidence unavailable")
        return sha256("|".join(fingerprints).encode("utf-8")).hexdigest()

    def _reauthorize(
        self,
        principal: PrincipalContext,
        candidates: Sequence[RetrievalCandidate],
    ) -> tuple[tuple[RetrievalCandidate, ...], int]:
        allowed: list[RetrievalCandidate] = []
        drops = 0
        for candidate in candidates:
            if candidate.tenant_id != principal.tenant_id:
                drops += 1
                continue
            try:
                decision = self.authorization.check(
                    principal, "can_view", candidate.resource_id
                )
            except AuthorizationUnavailable as exc:
                raise EvidenceAuthorizationError(
                    "authorized evidence unavailable"
                ) from exc
            if (
                decision.outcome is not AuthorizationOutcome.ALLOW
                or not decision.allowed
            ):
                drops += 1
                continue
            allowed.append(replace(candidate, authorization=decision))
        return tuple(allowed), drops

    def _load_materials(
        self, candidates: Sequence[RetrievalCandidate]
    ) -> tuple[EvidenceMaterial, ...]:
        if not candidates:
            return ()
        try:
            materials = tuple(self.content_store.load(candidates))
        except (OSError, RuntimeError) as exc:
            raise EvidenceContentUnavailable("authorized evidence unavailable") from exc
        candidates_by_chunk = {
            candidate.chunk_id: candidate for candidate in candidates
        }
        if len(materials) != len(candidates):
            raise EvidenceContentUnavailable("authorized evidence unavailable")
        verified: list[EvidenceMaterial] = []
        loaded_chunk_ids: set[str] = set()
        for material in materials:
            expected = candidates_by_chunk.get(material.candidate.chunk_id)
            if (
                expected is None
                or material.candidate.chunk_id in loaded_chunk_ids
                or material.candidate.resource_id != expected.resource_id
                or material.candidate.tenant_id != expected.tenant_id
                or material.candidate.document_version_id
                != expected.document_version_id
            ):
                raise EvidenceContentUnavailable("authorized evidence unavailable")
            loaded_chunk_ids.add(material.candidate.chunk_id)
            verified.append(replace(material, candidate=expected))
        return tuple(verified)

    def _prepare(
        self,
        materials: Sequence[EvidenceMaterial],
        candidates: Sequence[RetrievalCandidate],
    ) -> tuple[EvidenceResolutionInput, ...]:
        retrieval_ranks = {
            candidate.chunk_id: index for index, candidate in enumerate(candidates, 1)
        }
        prepared: list[EvidenceResolutionInput] = []
        for material in materials:
            text = normalize_untrusted_text(material.text).strip()
            if not text or len(text) > self.limits.max_evidence_text_chars:
                raise EvidenceContentUnavailable("authorized evidence unavailable")
            candidate = material.candidate
            prepared.append(
                EvidenceResolutionInput(
                    material=replace(material, text=text),
                    evidence_id=stable_evidence_id(
                        candidate.chunk_id, candidate.document_version_id
                    ),
                    sanitized_text=text,
                    retrieval_rank=retrieval_ranks[candidate.chunk_id],
                    rerank_rank=1,
                    rerank_score=None,
                    fallback_used=False,
                )
            )
        return tuple(prepared[: self.limits.max_rerank_candidates])

    def _rerank(
        self,
        question: str,
        prepared: Sequence[EvidenceResolutionInput],
    ) -> tuple[tuple[EvidenceResolutionInput, ...], bool]:
        if not prepared:
            return (), False
        chunks = tuple(
            AuthorizedChunk(
                object_id=item.material.candidate.resource_id,
                evidence_id=item.evidence_id,
                text=item.sanitized_text,
                tenant_id=item.material.candidate.tenant_id,
            )
            for item in prepared
        )
        try:
            scores = self.reranker.rerank(
                question,
                chunks,
                limit=len(chunks),
                timeout_ms=self.limits.reranker_timeout_ms,
            )
            return self._apply_scores(prepared, scores), False
        except (RerankerTimeout, RerankerUnavailable, TimeoutError):
            return tuple(
                replace(item, rerank_rank=index, rerank_score=None, fallback_used=True)
                for index, item in enumerate(prepared, 1)
            ), True

    @staticmethod
    def _apply_scores(
        prepared: Sequence[EvidenceResolutionInput],
        scores: Sequence[RerankScore],
    ) -> tuple[EvidenceResolutionInput, ...]:
        by_id = {item.evidence_id: item for item in prepared}
        ordered: list[EvidenceResolutionInput] = []
        seen: set[EvidenceId] = set()
        for rank, score in enumerate(scores, 1):
            item = by_id.get(score.evidence_id)
            if item is None or score.evidence_id in seen:
                raise RerankerUnavailable("reranker returned an invalid evidence ID")
            seen.add(score.evidence_id)
            ordered.append(
                replace(
                    item,
                    rerank_rank=rank,
                    rerank_score=score.score,
                    fallback_used=False,
                )
            )
        for item in prepared:
            if item.evidence_id not in seen:
                ordered.append(
                    replace(
                        item,
                        rerank_rank=len(ordered) + 1,
                        rerank_score=None,
                        fallback_used=False,
                    )
                )
        return tuple(ordered)

    @staticmethod
    def _resolution_inputs(
        ranked: Sequence[EvidenceResolutionInput], fallback_used: bool
    ) -> tuple[EvidenceResolutionInput, ...]:
        return tuple(replace(item, fallback_used=fallback_used) for item in ranked)
