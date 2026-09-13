"""Private-network OpenSearch index adapter with redacted failure handling."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from knowledge_system.domain.indexing import SearchIndexDocument


class OpenSearchAdapterError(RuntimeError):
    """OpenSearch failed without exposing response bodies or indexed content."""


@dataclass(frozen=True, slots=True)
class OpenSearchConfig:
    endpoint: str = "https://127.0.0.1:9200"
    username: str = "admin"
    password: str = ""
    timeout_seconds: float = 10.0
    verify_tls: bool = False

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host:
            raise ValueError("OpenSearch endpoint must be an HTTP(S) URL")
        if not _is_local_or_private(host):
            raise ValueError("OpenSearch endpoint must be localhost/private-network")
        if self.timeout_seconds <= 0 or not self.username.strip():
            raise ValueError("OpenSearch connection settings are invalid")


def _is_local_or_private(host: str) -> bool:
    if host in {"localhost", "opensearch"}:
        return True
    try:
        return (
            ipaddress.ip_address(host).is_private
            or ipaddress.ip_address(host).is_loopback
        )
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class OpenSearchResponse:
    status_code: int
    body: Mapping[str, object]


class OpenSearchTransport:
    """Small transport seam for tests and the local HTTP implementation."""

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: object | None = None,
        raw_body: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> OpenSearchResponse:
        raise NotImplementedError


class HttpxOpenSearchTransport(OpenSearchTransport):
    def __init__(self, config: OpenSearchConfig) -> None:
        self._client = httpx.Client(
            base_url=config.endpoint.rstrip("/"),
            auth=(config.username, config.password),
            timeout=config.timeout_seconds,
            verify=config.verify_tls,
            headers={"content-type": "application/json"},
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: object | None = None,
        raw_body: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> OpenSearchResponse:
        try:
            response = self._client.request(
                method, path, json=json_body, content=raw_body, headers=headers
            )
            body: object = response.json() if response.content else {}
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenSearchAdapterError("OpenSearch request failed") from exc
        if not isinstance(body, dict):
            body = {}
        return OpenSearchResponse(response.status_code, body)


_INDEX_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,126}$")


class OpenSearchIndexAdapter:
    def __init__(self, transport: OpenSearchTransport) -> None:
        self._transport = transport

    def create_generation(self, index_name: str, mapping: dict[str, object]) -> None:
        self._validate_index_name(index_name)
        self._request("PUT", f"/{index_name}", json_body={"mappings": mapping})

    def bulk_index(
        self, index_name: str, documents: Sequence[SearchIndexDocument]
    ) -> None:
        self._validate_index_name(index_name)
        if not documents:
            return
        lines: list[str] = []
        for document in documents:
            lines.append(
                json.dumps(
                    {"index": {"_index": index_name, "_id": document.document_id}}
                )
            )
            lines.append(
                json.dumps(document.fields, ensure_ascii=False, sort_keys=True)
            )
        response = self._request(
            "POST",
            "/_bulk",
            raw_body="\n".join(lines) + "\n",
            headers={"content-type": "application/x-ndjson"},
        )
        if response.body.get("errors") is True:
            raise OpenSearchAdapterError("OpenSearch bulk indexing reported an error")

    def activate_alias(self, index_name: str, alias: str) -> None:
        self._validate_index_name(index_name)
        self._validate_index_name(alias)
        self._request(
            "POST",
            "/_aliases",
            json_body={
                "actions": [
                    {"remove": {"alias": alias, "index": "knowledge-chunks-*"}},
                    {
                        "add": {
                            "alias": alias,
                            "index": index_name,
                            "is_write_index": True,
                        }
                    },
                ]
            },
        )

    def delete_chunk(self, index_name: str, chunk_id: str) -> None:
        self._validate_index_name(index_name)
        self._request("DELETE", f"/{index_name}/_doc/{self._safe_id(chunk_id)}")

    def delete_document(self, index_name: str, document_id: str) -> None:
        self._validate_index_name(index_name)
        self._request(
            "POST",
            f"/{index_name}/_delete_by_query",
            json_body={
                "query": {"term": {"document_id": document_id}},
                "conflicts": "proceed",
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: object | None = None,
        raw_body: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> OpenSearchResponse:
        response = self._transport.request(
            method,
            path,
            json_body=json_body,
            raw_body=raw_body,
            headers=headers,
        )
        if response.status_code >= 400:
            raise OpenSearchAdapterError(
                f"OpenSearch request failed with status {response.status_code}"
            )
        return response

    @staticmethod
    def _validate_index_name(index_name: str) -> None:
        if not _INDEX_RE.fullmatch(index_name):
            raise ValueError("unsafe OpenSearch index name")

    @staticmethod
    def _safe_id(value: str) -> str:
        if not value or "/" in value or "?" in value or "#" in value:
            raise ValueError("unsafe OpenSearch document ID")
        return value
