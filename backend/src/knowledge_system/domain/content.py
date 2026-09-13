"""Typed, metadata-complete content objects produced before search indexing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import NewType

from knowledge_system.domain.persistence import (
    Classification,
    DocumentId,
    DocumentMetadata,
    DocumentVersionId,
    TenantId,
    stable_chunk_id,
)

ContentBlockId = NewType("ContentBlockId", str)


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """A source-native location retained for later citation reconstruction."""

    kind: str
    value: str
    section_path: tuple[str, ...] = ()
    page_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    message_id: str | None = None
    thread_id: str | None = None
    ticket_id: str | None = None
    comment_id: str | None = None
    speaker: str | None = None
    turn_start: int | None = None
    turn_end: int | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.value.strip():
            raise ValueError("locator kind and value must not be empty")
        if any(not section.strip() for section in self.section_path):
            raise ValueError("locator section names must not be empty")
        for name in ("page_number", "line_start", "line_end", "turn_start", "turn_end"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("locator line range is invalid")
        if (
            self.turn_start is not None
            and self.turn_end is not None
            and self.turn_end < self.turn_start
        ):
            raise ValueError("locator turn range is invalid")

    def citation(self) -> str:
        """Return a stable, human-readable locator without source text."""

        parts = [f"{self.kind}:{self.value}"]
        if self.section_path:
            parts.append("section=" + " > ".join(self.section_path))
        if self.page_number is not None:
            parts.append(f"page={self.page_number}")
        if self.line_start is not None:
            end = self.line_end or self.line_start
            parts.append(f"lines={self.line_start}-{end}")
        if self.message_id:
            parts.append(f"message={self.message_id}")
        if self.thread_id:
            parts.append(f"thread={self.thread_id}")
        if self.ticket_id:
            parts.append(f"ticket={self.ticket_id}")
        if self.comment_id:
            parts.append(f"comment={self.comment_id}")
        if self.speaker:
            parts.append(f"speaker={self.speaker}")
        if self.turn_start is not None:
            end = self.turn_end or self.turn_start
            parts.append(f"turns={self.turn_start}-{end}")
        return "#".join(parts)


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """Untrusted source text plus its source-native location."""

    text: str
    locator: SourceLocator
    block_type: str = "paragraph"

    def __post_init__(self) -> None:
        if not self.block_type.strip():
            raise ValueError("block type must not be empty")


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    document_id: DocumentId
    metadata: DocumentMetadata
    raw_size_bytes: int
    blocks: tuple[ParsedBlock, ...]


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    document_id: DocumentId
    document_version_id: DocumentVersionId
    metadata: DocumentMetadata
    raw_size_bytes: int
    blocks: tuple[ParsedBlock, ...]


@dataclass(frozen=True, slots=True)
class ChunkingLimits:
    """Independent bounds for source bytes, lines, tokens, and chunk payloads."""

    max_document_bytes: int = 2 * 1024 * 1024
    max_document_chars: int = 2_000_000
    max_document_lines: int = 50_000
    max_chunk_chars: int = 4_000
    max_chunk_tokens: int = 800
    max_chunk_lines: int = 80
    max_thread_depth: int = 8
    max_transcript_turns: int = 8

    def __post_init__(self) -> None:
        names = (
            "max_document_bytes",
            "max_document_chars",
            "max_document_lines",
            "max_chunk_chars",
            "max_chunk_tokens",
            "max_chunk_lines",
            "max_thread_depth",
            "max_transcript_turns",
        )
        if any(getattr(self, name) < 1 for name in names):
            raise ValueError("content limits must be positive")


@dataclass(frozen=True, slots=True)
class ChunkingMetrics:
    input_bytes: int
    input_chars: int
    input_lines: int
    input_tokens: int
    output_chunks: int
    empty_blocks: int
    split_blocks: int


@dataclass(frozen=True, slots=True)
class ContentChunk:
    """A citation-ready chunk carrying all policy metadata downstream needs."""

    chunk_id: str
    document_id: DocumentId
    document_version_id: DocumentVersionId
    tenant_id: TenantId
    ordinal: int
    text: str
    metadata: DocumentMetadata
    locators: tuple[SourceLocator, ...]
    content_hash: str
    token_count: int
    line_count: int

    def __post_init__(self) -> None:
        if (
            not self.chunk_id.strip()
            or not self.text.strip()
            or self.ordinal < 0
            or not self.locators
            or self.token_count < 1
            or self.line_count < 1
        ):
            raise ValueError("content chunk identity, text, and locators are required")
        if self.metadata.tenant_id != self.tenant_id:
            raise ValueError("chunk tenant must match metadata tenant")

    @property
    def citation_locators(self) -> tuple[str, ...]:
        return tuple(locator.citation() for locator in self.locators)


_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def token_count(text: str) -> int:
    """Count deterministic lexical tokens without coupling to a model tokenizer."""

    return len(_TOKEN_RE.findall(text))


def content_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def build_content_chunk(
    document_id: DocumentId,
    document_version_id: DocumentVersionId,
    metadata: DocumentMetadata,
    ordinal: int,
    text: str,
    locators: tuple[SourceLocator, ...],
) -> ContentChunk:
    digest = content_hash(text)
    return ContentChunk(
        chunk_id=str(stable_chunk_id(document_id, metadata.version, ordinal, digest)),
        document_id=document_id,
        document_version_id=document_version_id,
        tenant_id=metadata.tenant_id,
        ordinal=ordinal,
        text=text,
        metadata=metadata,
        locators=locators,
        content_hash=digest,
        token_count=token_count(text),
        line_count=text.count("\n") + 1,
    )


def resolve_classification(value: object | None) -> Classification:
    """Apply the conservative deterministic default to missing/unknown values."""

    if isinstance(value, Classification):
        return value
    if isinstance(value, str):
        try:
            return Classification(value.upper())
        except ValueError:
            pass
    return Classification.RESTRICTED
