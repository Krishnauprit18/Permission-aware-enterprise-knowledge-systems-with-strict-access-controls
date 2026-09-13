"""Private-network OpenSearch index adapter with redacted failure handling."""

from __future__ import annotations

import ipaddress
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from knowledge_system.domain.contracts import AuthorizedObjectId, CandidateEnvelope
from knowledge_system.domain.indexing import SearchIndexDocument
from knowledge_system.domain.retrieval import EffectiveSearchFilter


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
            trust_env=False,
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
        except httpx.HTTPError as exc:
            raise OpenSearchAdapterError("OpenSearch request failed") from exc
        if response.content:
            try:
                body: object = response.json()
            except ValueError:
                body = {}
        else:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return OpenSearchResponse(response.status_code, body)


_INDEX_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,126}$")


class OpenSearchIndexAdapter:
    def __init__(self, transport: OpenSearchTransport) -> None:
        self._transport = transport

    def create_generation(self, index_name: str, mapping: dict[str, object]) -> None:
        self._validate_index_name(index_name)
        self._request(
            "PUT",
            f"/{index_name}",
            json_body={"settings": {"index.knn": True}, "mappings": mapping},
        )

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
            "/_bulk?refresh=wait_for",
            raw_body="\n".join(lines) + "\n",
            headers={"content-type": "application/x-ndjson"},
        )
        if response.body.get("errors") is True:
            raise OpenSearchAdapterError("OpenSearch bulk indexing reported an error")

    def activate_alias(self, index_name: str, alias: str) -> None:
        self._validate_index_name(index_name)
        self._validate_index_name(alias)
        existing = self._transport.request("GET", f"/_alias/{alias}")
        if existing.status_code not in {200, 404}:
            raise OpenSearchAdapterError(
                f"OpenSearch alias lookup failed with status {existing.status_code}"
            )
        actions: list[dict[str, object]] = []
        if existing.status_code == 200:
            for existing_index in existing.body:
                self._validate_index_name(existing_index)
                actions.append({"remove": {"alias": alias, "index": existing_index}})
        actions.append(
            {
                "add": {
                    "alias": alias,
                    "index": index_name,
                    "is_write_index": True,
                }
            }
        )
        self._request(
            "POST",
            "/_aliases",
            json_body={"actions": actions},
        )

    def search_bm25(
        self, index_name: str, query: str, size: int = 10
    ) -> OpenSearchResponse:
        self._validate_index_name(index_name)
        if not query.strip() or not 1 <= size <= 100:
            raise ValueError("BM25 query and size are invalid")
        return self._request(
            "GET",
            f"/{index_name}/_search",
            json_body={"size": size, "query": {"match": {"text": query}}},
        )

    def search_knn(
        self, index_name: str, vector: Sequence[float], k: int = 10
    ) -> OpenSearchResponse:
        self._validate_index_name(index_name)
        if (
            not vector
            or not 1 <= k <= 100
            or any(not math.isfinite(value) for value in vector)
        ):
            raise ValueError("vector query and k are invalid")
        return self._request(
            "GET",
            f"/{index_name}/_search",
            json_body={
                "size": k,
                "query": {"knn": {"vector": {"vector": list(vector), "k": k}}},
            },
        )

    def search_bm25_candidates(
        self,
        query: str,
        filters: EffectiveSearchFilter,
        size: int,
        *,
        index_name: str = "knowledge-chunks-active",
    ) -> tuple[CandidateEnvelope, ...]:
        """Search with server-owned filters and return metadata only."""

        self._validate_index_name(index_name)
        self._validate_query_size(query, size)
        response = self._request(
            "GET",
            f"/{index_name}/_search",
            json_body={
                "_source": self._candidate_source_fields(),
                "size": size,
                "query": {
                    "bool": {
                        "must": [{"match": {"text": query}}],
                        "filter": [self._filter_clause(filters)],
                    }
                },
            },
        )
        return self._candidate_hits(response, score_field="lexical_score")

    def search_vector_candidates(
        self,
        vector: Sequence[float],
        filters: EffectiveSearchFilter,
        size: int,
        *,
        index_name: str = "knowledge-chunks-active",
    ) -> tuple[CandidateEnvelope, ...]:
        """Run ANN search inside the same mandatory authorization filter."""

        self._validate_index_name(index_name)
        if (
            not 1 <= size <= 100
            or not vector
            or any(not math.isfinite(value) for value in vector)
        ):
            raise ValueError("vector query and size are invalid")
        response = self._request(
            "GET",
            f"/{index_name}/_search",
            json_body={
                "_source": self._candidate_source_fields(),
                "size": size,
                "query": {
                    "knn": {
                        "vector": {
                            "vector": list(vector),
                            "k": size,
                            "filter": self._filter_clause(filters),
                        }
                    }
                },
            },
        )
        return self._candidate_hits(response, score_field="vector_score")

    def delete_chunk(self, index_name: str, chunk_id: str) -> None:
        self._validate_index_name(index_name)
        self._request(
            "DELETE",
            f"/{index_name}/_doc/{self._safe_id(chunk_id)}?refresh=wait_for",
        )

    def delete_document(self, index_name: str, document_id: str) -> None:
        self._validate_index_name(index_name)
        self._request(
            "POST",
            f"/{index_name}/_delete_by_query?refresh=wait_for",
            json_body={
                "query": {"term": {"document_id": document_id}},
                "conflicts": "proceed",
            },
        )

    def delete_generation(self, index_name: str) -> None:
        """Remove a disposable physical generation after a verified cutover."""

        self._validate_index_name(index_name)
        self._request("DELETE", f"/{index_name}")

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
    def _validate_query_size(query: str, size: int) -> None:
        if not query.strip() or len(query) > 2_000 or not 1 <= size <= 100:
            raise ValueError("query and size are invalid")

    @staticmethod
    def _candidate_source_fields() -> list[str]:
        return [
            "chunk_id",
            "document_id",
            "document_version_id",
            "tenant_id",
            "source_type",
            "source_external_id",
            "account_ids",
            "department",
            "classification",
            "citation_locators",
            "updated_at",
            "source_url",
            "author",
            "language",
            "authority_level",
            "status",
            "acl_relationship_refs",
        ]

    @staticmethod
    def _filter_clause(filters: EffectiveSearchFilter) -> dict[str, object]:
        if not filters.has_authorized_resources:
            return {"match_none": {}}
        clauses: list[dict[str, object]] = [
            {"term": {"tenant_id": filters.authorization.tenant_id}},
            {"terms": {"document_id": list(filters.authorization.document_ids)}},
        ]
        if filters.account_ids:
            clauses.append({"terms": {"account_ids": list(filters.account_ids)}})
        if filters.department is not None:
            clauses.append({"term": {"department": filters.department}})
        date_range: dict[str, str] = {}
        if filters.updated_after is not None:
            date_range["gte"] = filters.updated_after.isoformat()
        if filters.updated_before is not None:
            date_range["lte"] = filters.updated_before.isoformat()
        if date_range:
            clauses.append({"range": {"updated_at": date_range}})
        return {"bool": {"filter": clauses}}

    @staticmethod
    def _candidate_hits(
        response: OpenSearchResponse, *, score_field: str
    ) -> tuple[CandidateEnvelope, ...]:
        hits_container = response.body.get("hits")
        if not isinstance(hits_container, Mapping):
            return ()
        raw_hits = hits_container.get("hits")
        if not isinstance(raw_hits, list):
            return ()
        candidates: list[CandidateEnvelope] = []
        for raw_hit in raw_hits:
            if not isinstance(raw_hit, Mapping):
                continue
            source = raw_hit.get("_source")
            if not isinstance(source, Mapping):
                continue
            candidate = OpenSearchIndexAdapter._candidate_from_source(
                source, raw_hit.get("_score"), score_field
            )
            if candidate is not None:
                candidates.append(candidate)
        return tuple(candidates)

    @staticmethod
    def _candidate_from_source(
        source: Mapping[str, object], score: object, score_field: str
    ) -> CandidateEnvelope | None:
        required = ("chunk_id", "document_id", "document_version_id", "tenant_id")
        if any(not isinstance(source.get(field), str) for field in required):
            return None
        chunk_id = str(source["chunk_id"])
        document_id = str(source["document_id"])
        document_version_id = str(source["document_version_id"])
        tenant_id = str(source["tenant_id"])
        if not chunk_id or not document_id or not tenant_id:
            return None
        if not isinstance(source.get("source_type"), str) or not isinstance(
            source.get("classification"), str
        ):
            return None
        account_ids = source.get("account_ids")
        locators = source.get("citation_locators")
        if not isinstance(account_ids, list) or not all(
            isinstance(value, str) for value in account_ids
        ):
            return None
        if not isinstance(locators, list) or not all(
            isinstance(value, str) for value in locators
        ):
            return None
        updated_at = source.get("updated_at")
        if not isinstance(updated_at, str):
            return None
        numeric_score = float(score) if isinstance(score, (int, float)) else None
        raw_acl_refs = source.get("acl_relationship_refs", [])
        acl_refs = (
            [value for value in raw_acl_refs if isinstance(value, str)]
            if isinstance(raw_acl_refs, list)
            else []
        )
        provenance = {
            "source_external_id": str(source.get("source_external_id", document_id)),
            "account_ids": ",".join(account_ids),
            "department": str(source.get("department", "")),
            "citation_locators": "\x1f".join(locators),
            "updated_at": updated_at,
            "source_url": str(source.get("source_url", "")),
            "author": str(source.get("author", "")),
            "language": str(source.get("language", "")),
            "authority_level": str(source.get("authority_level", "")),
            "status": str(source.get("status", "")),
            "acl_relationship_refs": "\x1f".join(acl_refs),
        }
        return CandidateEnvelope(
            object_id=AuthorizedObjectId(f"resource:{document_id}"),
            tenant_id=tenant_id,
            source=str(source["source_type"]),
            access_level=str(source["classification"]),
            chunk_id=chunk_id,
            document_id=document_id,
            document_version_id=document_version_id,
            lexical_score=numeric_score if score_field == "lexical_score" else None,
            vector_score=numeric_score if score_field == "vector_score" else None,
            provenance=provenance,
        )

    @staticmethod
    def _validate_index_name(index_name: str) -> None:
        if not _INDEX_RE.fullmatch(index_name):
            raise ValueError("unsafe OpenSearch index name")

    @staticmethod
    def _safe_id(value: str) -> str:
        if not value or "/" in value or "?" in value or "#" in value:
            raise ValueError("unsafe OpenSearch document ID")
        return value
