"""Application service for parsing, normalization, and bounded chunking."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace

from knowledge_system.application.ports.content import (
    ContentChunker,
    ContentNormalizer,
    ContentParser,
)
from knowledge_system.domain.content import (
    ChunkingLimits,
    ChunkingMetrics,
    ContentChunk,
    NormalizedDocument,
    ParsedBlock,
    ParsedDocument,
    SourceLocator,
    build_content_chunk,
    resolve_classification,
    token_count,
)
from knowledge_system.domain.ingestion import SourceEnvelope
from knowledge_system.domain.persistence import Classification, DocumentVersionId


class ContentLimitExceeded(ValueError):
    """The content cannot be processed within the configured resource bounds."""


_ACTIVE_BLOCK_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed|svg)\b[^>]*>.*?</\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


def normalize_untrusted_text(value: str) -> str:
    """Normalize text only; markup and macro contents are never executed."""

    value = unicodedata.normalize("NFC", value)
    value = _ACTIVE_BLOCK_RE.sub("", value)
    value = _HTML_COMMENT_RE.sub("", value)
    value = _HTML_TAG_RE.sub("", value)
    cleaned: list[str] = []
    for character in value:
        if character in {"\n", "\t"} or ord(character) >= 32:
            cleaned.append(character)
    return "".join(cleaned).replace("\r\n", "\n").replace("\r", "\n")


@dataclass(frozen=True, slots=True)
class SafeContentNormalizer(ContentNormalizer):
    limits: ChunkingLimits = field(default_factory=ChunkingLimits)

    def normalize(self, parsed: ParsedDocument) -> NormalizedDocument:
        if parsed.raw_size_bytes > self.limits.max_document_bytes:
            raise ContentLimitExceeded("document exceeds byte limit")
        normalized_blocks: list[ParsedBlock] = []
        for block in parsed.blocks:
            text = normalize_untrusted_text(block.text)
            if text.strip():
                normalized_blocks.append(replace(block, text=text))
        combined = "\n\n".join(block.text for block in normalized_blocks)
        if len(combined) > self.limits.max_document_chars:
            raise ContentLimitExceeded("document exceeds character limit")
        line_count = combined.count("\n") + (1 if combined else 0)
        if line_count > self.limits.max_document_lines:
            raise ContentLimitExceeded("document exceeds line limit")
        classification = resolve_classification(parsed.metadata.classification)
        shareable = parsed.metadata.external_shareable and classification in {
            Classification.PUBLIC,
            Classification.CUSTOMER_SHAREABLE,
        }
        metadata = replace(
            parsed.metadata,
            classification=classification,
            external_shareable=shareable,
        )
        version_id = DocumentVersionId(f"{parsed.document_id}:v{metadata.version}")
        return NormalizedDocument(
            document_id=parsed.document_id,
            document_version_id=version_id,
            metadata=metadata,
            raw_size_bytes=parsed.raw_size_bytes,
            blocks=tuple(normalized_blocks),
        )


@dataclass(frozen=True, slots=True)
class BoundedContentChunker(ContentChunker):
    limits: ChunkingLimits = field(default_factory=ChunkingLimits)

    def chunk(
        self, document: NormalizedDocument
    ) -> tuple[tuple[ContentChunk, ...], ChunkingMetrics]:
        input_text = "\n\n".join(block.text for block in document.blocks)
        metrics = ChunkingMetrics(
            input_bytes=document.raw_size_bytes,
            input_chars=len(input_text),
            input_lines=input_text.count("\n") + (1 if input_text else 0),
            input_tokens=token_count(input_text),
            output_chunks=0,
            empty_blocks=0,
            split_blocks=0,
        )
        pieces: list[tuple[str, tuple[SourceLocator, ...]]] = []
        empty_blocks = 0
        split_blocks = 0
        for block in document.blocks:
            if not block.text.strip():
                empty_blocks += 1
                continue
            block_parts = self._split_block(block)
            if len(block_parts) > 1:
                split_blocks += 1
            pieces.extend((text, (block.locator,)) for text in block_parts)

        packed: list[tuple[str, tuple[SourceLocator, ...]]] = []
        current_text = ""
        current_locators: list[SourceLocator] = []
        for text, locators in pieces:
            candidate = f"{current_text}\n\n{text}" if current_text else text
            if current_text and not self._fits(candidate):
                packed.append((current_text, tuple(current_locators)))
                current_text = text
                current_locators = list(locators)
            else:
                current_text = candidate
                for locator in locators:
                    if locator not in current_locators:
                        current_locators.append(locator)
        if current_text:
            packed.append((current_text, tuple(current_locators)))

        chunks = tuple(
            build_content_chunk(
                document.document_id,
                document.document_version_id,
                document.metadata,
                ordinal,
                text,
                locators,
            )
            for ordinal, (text, locators) in enumerate(packed)
        )
        return chunks, replace(
            metrics,
            output_chunks=len(chunks),
            empty_blocks=empty_blocks,
            split_blocks=split_blocks,
        )

    def _fits(self, text: str) -> bool:
        return (
            len(text) <= self.limits.max_chunk_chars
            and token_count(text) <= self.limits.max_chunk_tokens
            and text.count("\n") + 1 <= self.limits.max_chunk_lines
        )

    def _split_block(self, block: ParsedBlock) -> list[str]:
        if self._fits(block.text):
            return [block.text]
        parts: list[str] = []
        current_lines: list[str] = []
        for line in block.text.splitlines() or [block.text]:
            line_parts = self._split_line(line)
            for line_part in line_parts:
                candidate = "\n".join((*current_lines, line_part))
                if current_lines and not self._fits(candidate):
                    parts.append("\n".join(current_lines))
                    current_lines = [line_part]
                else:
                    current_lines.append(line_part)
                    if not self._fits("\n".join(current_lines)):
                        parts.append("\n".join(current_lines[:-1]))
                        current_lines = [line_part]
        if current_lines:
            parts.append("\n".join(current_lines))
        return [part for part in parts if part.strip()]

    def _split_line(self, line: str) -> list[str]:
        if self._fits(line):
            return [line]
        words = line.split()
        if not words:
            return [line[: self.limits.max_chunk_chars]]
        parts: list[str] = []
        current = ""
        for word in words:
            if len(word) > self.limits.max_chunk_chars:
                if current:
                    parts.append(current)
                    current = ""
                width = min(self.limits.max_chunk_chars, self.limits.max_chunk_tokens)
                parts.extend(
                    word[index : index + width] for index in range(0, len(word), width)
                )
                continue
            candidate = f"{current} {word}".strip()
            if current and not self._fits(candidate):
                parts.append(current)
                current = word
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts


@dataclass(frozen=True, slots=True)
class ContentPipeline:
    parser: ContentParser
    normalizer: ContentNormalizer
    chunker: ContentChunker

    def process(
        self, envelope: SourceEnvelope
    ) -> tuple[tuple[ContentChunk, ...], ChunkingMetrics]:
        parsed = self.parser.parse(envelope)
        normalized = self.normalizer.normalize(parsed)
        return self.chunker.chunk(normalized)
