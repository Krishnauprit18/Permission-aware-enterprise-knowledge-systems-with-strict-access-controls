"""Local-only structured answer adapter for an Ollama-compatible runtime."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from threading import BoundedSemaphore
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from knowledge_system.application.generation import (
    GenerationModelTimeout,
    GenerationModelUnavailable,
)
from knowledge_system.application.ports.knowledge import GroundedLLM
from knowledge_system.domain.contracts import EvidenceId
from knowledge_system.domain.generation import (
    AuthorizedGenerationContext,
    CitationProposal,
    ModelClaim,
    ModelDraft,
)

_DEFAULT_ENDPOINT = "http://127.0.0.1:11434/api/chat"
_DEFAULT_MODEL_NAME = "qwen2.5:3b-instruct-q4_K_M"
_DEFAULT_MODEL_VERSION = "operator-managed-local"
_DEFAULT_TIMEOUT_MS = 8_000
_DEFAULT_MAX_OUTPUT_TOKENS = 512
_DEFAULT_MAX_CONCURRENCY = 1


class LocalModelTransport(Protocol):
    """Small transport surface that cannot expose arbitrary model tools."""

    def post(
        self, endpoint: str, payload: Mapping[str, object], *, timeout_s: float
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class LocalGenerationConfig:
    """Externalized local runtime settings; non-loopback endpoints are rejected."""

    endpoint: str = _DEFAULT_ENDPOINT
    model_name: str = _DEFAULT_MODEL_NAME
    model_version: str = _DEFAULT_MODEL_VERSION
    timeout_ms: int = _DEFAULT_TIMEOUT_MS
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS
    max_concurrency: int = _DEFAULT_MAX_CONCURRENCY

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("local generation endpoint must be loopback HTTP")
        if not self.model_name.strip() or not self.model_version.strip():
            raise ValueError("local generation model identity is required")
        if not 100 <= self.timeout_ms <= 60_000:
            raise ValueError("local generation timeout is invalid")
        if not 32 <= self.max_output_tokens <= 2_048:
            raise ValueError("local generation token budget is invalid")
        if not 1 <= self.max_concurrency <= 8:
            raise ValueError("local generation concurrency limit is invalid")

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> LocalGenerationConfig:
        values = os.environ if environ is None else environ
        return cls(
            endpoint=values.get("LOCAL_LLM_ENDPOINT", _DEFAULT_ENDPOINT),
            model_name=values.get("LOCAL_LLM_MODEL", _DEFAULT_MODEL_NAME),
            model_version=values.get("LOCAL_LLM_MODEL_VERSION", _DEFAULT_MODEL_VERSION),
            timeout_ms=int(
                values.get("LOCAL_LLM_TIMEOUT_MS", str(_DEFAULT_TIMEOUT_MS))
            ),
            max_output_tokens=int(
                values.get(
                    "LOCAL_LLM_MAX_OUTPUT_TOKENS", str(_DEFAULT_MAX_OUTPUT_TOKENS)
                )
            ),
            max_concurrency=int(
                values.get("LOCAL_LLM_MAX_CONCURRENCY", str(_DEFAULT_MAX_CONCURRENCY))
            ),
        )


class HttpxLocalModelTransport(LocalModelTransport):
    """POST only the fixed chat schema to the configured local endpoint."""

    def post(
        self, endpoint: str, payload: Mapping[str, object], *, timeout_s: float
    ) -> Mapping[str, object]:
        try:
            with httpx.Client(timeout=timeout_s, trust_env=False) as client:
                response = client.post(endpoint, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise GenerationModelTimeout("local model timed out") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise GenerationModelUnavailable("local model is unavailable") from exc
        if not isinstance(body, dict):
            raise GenerationModelUnavailable("local model returned an invalid response")
        return body


class LocalOllamaGenerationAdapter(GroundedLLM):
    """Generate structured drafts locally; source data never enters the system prompt."""

    def __init__(
        self,
        config: LocalGenerationConfig,
        *,
        transport: LocalModelTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or HttpxLocalModelTransport()
        self._slots = BoundedSemaphore(config.max_concurrency)

    @property
    def model_id(self) -> str:
        return self._config.model_name

    @property
    def model_version(self) -> str:
        return self._config.model_version

    def generate(
        self, context: AuthorizedGenerationContext, *, retry: bool
    ) -> ModelDraft:
        if not self._slots.acquire(blocking=False):
            raise GenerationModelUnavailable("local model concurrency limit reached")
        try:
            response = self._transport.post(
                self._config.endpoint,
                self._payload(context, retry=retry),
                timeout_s=self._config.timeout_ms / 1_000,
            )
        finally:
            self._slots.release()
        return _draft_from_response(response)

    def _payload(
        self, context: AuthorizedGenerationContext, *, retry: bool
    ) -> Mapping[str, object]:
        retry_message = (
            "The prior draft failed citation validation. Return only a corrected JSON "
            "draft using supplied evidence IDs and exact supporting quotes."
            if retry
            else "Return one JSON draft now."
        )
        return {
            "format": _MODEL_DRAFT_SCHEMA,
            "model": self._config.model_name,
            "options": {"num_predict": self._config.max_output_tokens},
            "stream": False,
            "messages": [
                {"role": "system", "content": context.prompt.instructions},
                {"role": "user", "content": context.question},
                {
                    "role": "user",
                    "content": "UNTRUSTED_EVIDENCE_DATA_JSON\n"
                    + context.evidence_data_json(),
                },
                {"role": "user", "content": retry_message},
            ],
        }


_MODEL_DRAFT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["insufficient_evidence", "claims"],
    "properties": {
        "insufficient_evidence": {"type": "boolean"},
        "claims": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "citations"],
                "properties": {
                    "text": {"type": "string", "minLength": 1, "maxLength": 1200},
                    "citations": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["evidence_id", "quote"],
                            "properties": {
                                "evidence_id": {"type": "string", "minLength": 1},
                                "quote": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": 500,
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


def _draft_from_response(response: Mapping[str, object]) -> ModelDraft:
    """Parse the local runtime response without exposing its body in an error."""

    message = response.get("message")
    if not isinstance(message, Mapping):
        raise GenerationModelUnavailable("local model returned an invalid response")
    content = message.get("content")
    if not isinstance(content, str):
        raise GenerationModelUnavailable("local model returned an invalid response")
    try:
        value: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise GenerationModelUnavailable(
            "local model returned an invalid response"
        ) from exc
    if not isinstance(value, dict):
        raise GenerationModelUnavailable("local model returned an invalid response")
    insufficient = value.get("insufficient_evidence")
    claims_value = value.get("claims")
    if not isinstance(insufficient, bool) or not isinstance(claims_value, list):
        raise GenerationModelUnavailable("local model returned an invalid response")
    claims: list[ModelClaim] = []
    try:
        for claim_value in claims_value:
            if not isinstance(claim_value, dict):
                raise TypeError("claim is invalid")
            text = claim_value.get("text")
            citations_value = claim_value.get("citations")
            if not isinstance(text, str) or not isinstance(citations_value, list):
                raise TypeError("claim is invalid")
            citations: list[CitationProposal] = []
            for citation_value in citations_value:
                if not isinstance(citation_value, dict):
                    raise TypeError("citation is invalid")
                evidence_id = citation_value.get("evidence_id")
                quote = citation_value.get("quote")
                if not isinstance(evidence_id, str) or not isinstance(quote, str):
                    raise TypeError("citation is invalid")
                citations.append(
                    CitationProposal(evidence_id=EvidenceId(evidence_id), quote=quote)
                )
            claims.append(ModelClaim(text=text, citations=tuple(citations)))
        return ModelDraft(claims=tuple(claims), insufficient_evidence=insufficient)
    except (TypeError, ValueError) as exc:
        raise GenerationModelUnavailable(
            "local model returned an invalid response"
        ) from exc
