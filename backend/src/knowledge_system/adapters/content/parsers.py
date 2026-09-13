"""Source-aware parsers for bounded synthetic enterprise records."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from knowledge_system.domain.content import (
    ChunkingLimits,
    ParsedBlock,
    ParsedDocument,
    SourceLocator,
)
from knowledge_system.domain.ingestion import SourceEnvelope


class ContentInputError(ValueError):
    """A source record cannot safely become a content document."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ContentInputError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ContentInputError(f"{label} must be text")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContentInputError(f"{label} must be a JSON array")
    return cast(Sequence[object], value)


@dataclass(frozen=True, slots=True)
class FixtureContentParser:
    """Parse P09 envelopes using source-native structure and stable locators."""

    limits: ChunkingLimits = field(default_factory=ChunkingLimits)

    def parse(self, envelope: SourceEnvelope) -> ParsedDocument:
        raw = envelope.raw_content
        if raw is None:
            raise ContentInputError("deleted or empty source has no parseable body")
        if len(raw) > self.limits.max_document_bytes:
            raise ContentInputError("source document exceeds byte limit")
        source_type = envelope.metadata.source_type
        if source_type in {"document", "policy", "contract"}:
            blocks = self._markdown(raw, envelope)
        elif source_type == "slack_thread":
            blocks = self._slack(raw, envelope)
        elif source_type == "support_ticket":
            blocks = self._ticket(raw, envelope)
        elif source_type == "call_transcript":
            blocks = self._transcript(raw, envelope)
        elif source_type == "hourly_feed":
            blocks = self._generic_json(raw, envelope)
        else:
            raise ContentInputError(f"unsupported source type: {source_type}")
        return ParsedDocument(
            document_id=envelope.document_id,
            metadata=envelope.metadata,
            raw_size_bytes=len(raw),
            blocks=tuple(blocks),
        )

    def _markdown(self, raw: bytes, envelope: SourceEnvelope) -> list[ParsedBlock]:
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        blocks: list[ParsedBlock] = []
        current: list[str] = []
        start_line = 1
        section_path: list[str] = []
        fence_open = False
        source_id = envelope.metadata.source_external_id

        def flush(end_line: int) -> None:
            nonlocal current, start_line
            if current:
                blocks.append(
                    ParsedBlock(
                        text="\n".join(current),
                        locator=SourceLocator(
                            kind=envelope.metadata.source_type,
                            value=source_id,
                            section_path=tuple(section_path),
                            line_start=start_line,
                            line_end=end_line,
                        ),
                        block_type="code" if fence_open else "paragraph",
                    )
                )
                current = []

        for line_number, line in enumerate(lines, start=1):
            heading = None if fence_open else re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if heading:
                flush(line_number - 1)
                level = len(heading.group(1))
                title = heading.group(2).strip()
                section_path[:] = section_path[: level - 1]
                section_path.append(title)
                blocks.append(
                    ParsedBlock(
                        text=line,
                        locator=SourceLocator(
                            kind=envelope.metadata.source_type,
                            value=source_id,
                            section_path=tuple(section_path),
                            line_start=line_number,
                            line_end=line_number,
                        ),
                        block_type="heading",
                    )
                )
                start_line = line_number + 1
                continue
            if line.strip().startswith("```"):
                if not current:
                    start_line = line_number
                current.append(line)
                fence_open = not fence_open
                continue
            if not line.strip() and not fence_open:
                flush(line_number - 1)
                start_line = line_number + 1
                continue
            if not current:
                start_line = line_number
            current.append(line)
        flush(max(1, len(lines)))
        return blocks

    def _json(self, raw: bytes) -> Mapping[str, object]:
        try:
            return _mapping(json.loads(raw.decode("utf-8", errors="strict")), "record")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContentInputError("malformed JSON source record") from exc

    def _slack(self, raw: bytes, envelope: SourceEnvelope) -> list[ParsedBlock]:
        record = self._json(raw)
        thread_id = _text(record.get("thread_id"), "thread_id")
        blocks: list[ParsedBlock] = []
        ordinal = 0

        def walk(message: Mapping[str, object], depth: int) -> None:
            nonlocal ordinal
            if depth > self.limits.max_thread_depth:
                raise ContentInputError("Slack thread exceeds nesting limit")
            message_id = _text(message.get("message_id"), "message_id")
            author = _text(message.get("author", "unknown"), "author")
            body = _text(message.get("text"), "text")
            sent_at = message.get("sent_at", "unknown")
            blocks.append(
                ParsedBlock(
                    text=f"{author} ({sent_at}): {body}",
                    locator=SourceLocator(
                        kind="slack_message",
                        value=envelope.metadata.source_external_id,
                        message_id=message_id,
                        thread_id=thread_id,
                        section_path=(str(record.get("channel", "unknown")),),
                    ),
                    block_type="thread_message" if depth else "parent_message",
                )
            )
            ordinal += 1
            replies = message.get("replies", message.get("thread_replies", []))
            for reply in _sequence(replies, "replies"):
                walk(_mapping(reply, "reply"), depth + 1)

        for message in _sequence(record.get("messages"), "messages"):
            walk(_mapping(message, "message"), 0)
        if not blocks:
            raise ContentInputError("Slack thread has no messages")
        return blocks

    def _ticket(self, raw: bytes, envelope: SourceEnvelope) -> list[ParsedBlock]:
        record = self._json(raw)
        ticket_id = _text(record.get("ticket_id"), "ticket_id")
        metadata = " | ".join(
            f"{key}: {record[key]}"
            for key in ("title", "status", "opened_at", "updated_at", "assignee")
            if key in record
        )
        blocks = [
            ParsedBlock(
                text=metadata,
                locator=SourceLocator(
                    kind="support_ticket",
                    value=envelope.metadata.source_external_id,
                    ticket_id=ticket_id,
                ),
                block_type="ticket_metadata",
            )
        ]
        comments = _sequence(record.get("comments", []), "comments")
        for index, comment in enumerate(comments, start=1):
            if isinstance(comment, str):
                body = comment
                comment_id = f"{ticket_id}-comment-{index}"
            else:
                item = _mapping(comment, "comment")
                body = _text(item.get("text"), "comment.text")
                comment_id = _text(
                    item.get("comment_id", f"{ticket_id}-comment-{index}"), "comment_id"
                )
            blocks.append(
                ParsedBlock(
                    text=f"Comment {index}: {body}",
                    locator=SourceLocator(
                        kind="support_ticket_comment",
                        value=envelope.metadata.source_external_id,
                        ticket_id=ticket_id,
                        comment_id=comment_id,
                    ),
                    block_type="ticket_comment",
                )
            )
        return blocks

    def _transcript(self, raw: bytes, envelope: SourceEnvelope) -> list[ParsedBlock]:
        record = self._json(raw)
        call_id = _text(record.get("call_id"), "call_id")
        turns = _sequence(record.get("transcript"), "transcript")
        blocks: list[ParsedBlock] = []
        window = self.limits.max_transcript_turns
        for start in range(0, len(turns), window):
            selected = turns[start : start + window]
            rendered: list[str] = []
            for offset, turn in enumerate(selected, start=start + 1):
                if isinstance(turn, str):
                    rendered.append(f"Turn {offset}: {turn}")
                else:
                    item = _mapping(turn, "transcript turn")
                    speaker = _text(item.get("speaker", "unknown"), "speaker")
                    body = _text(item.get("text"), "turn.text")
                    rendered.append(f"{speaker}: {body}")
            if rendered:
                blocks.append(
                    ParsedBlock(
                        text="\n".join(rendered),
                        locator=SourceLocator(
                            kind="call_transcript",
                            value=envelope.metadata.source_external_id,
                            ticket_id=None,
                            section_path=(call_id,),
                            turn_start=start + 1,
                            turn_end=start + len(selected),
                        ),
                        block_type="transcript_window",
                    )
                )
        return blocks

    def _generic_json(self, raw: bytes, envelope: SourceEnvelope) -> list[ParsedBlock]:
        record = self._json(raw)
        text = json.dumps(record, ensure_ascii=False, sort_keys=True)
        return [
            ParsedBlock(
                text=text,
                locator=SourceLocator(
                    kind=envelope.metadata.source_type,
                    value=envelope.metadata.source_external_id,
                ),
                block_type="structured_record",
            )
        ]
