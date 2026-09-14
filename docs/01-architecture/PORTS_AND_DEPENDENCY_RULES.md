# Ports and Dependency Rules

## 1. Layering

The backend is a modular monolith with ports and adapters. The goal is clear
security ownership and replaceable infrastructure, not a framework abstraction
for every function.

```text
domain
  <- application (use cases and ports)
       <- adapters (FastAPI, PostgreSQL, OpenSearch, OpenFGA, Keycloak,
                    MinIO, local models, OpenTelemetry)
       <- entrypoints (API and worker delivery)
bootstrap/composition root wires adapters to ports
```

Recommended repository shape for the implementation phase:

```text
backend/
  src/knowledge_system/
    domain/
    application/
      ports/
      use_cases/
    adapters/
      auth/
      identity/
      persistence/
      search/
      object_store/
      models/
      observability/
    entrypoints/
      api/
      worker/
    bootstrap/
  tests/
frontend/
  src/
    app/
    features/
    shared/
```

## 2. Import rules

- `domain` imports only the Python standard library and approved pure typing
  helpers. It contains identifiers, value objects, invariants, and deterministic
  policy/evidence rules, not FastAPI, OpenSearch, OpenFGA, or database types.
- `application` imports `domain`. It defines use cases and ports. It does not
  import concrete adapters or framework request/response objects.
- `adapters` import `application` ports and `domain` types. They translate
  external SDK/protocol data at the boundary and never leak vendor objects into
  application code.
- `entrypoints` import application use cases and transport DTO mappers. Route
  handlers and worker commands do not instantiate infrastructure clients.
- `bootstrap` is the only backend module allowed to import concrete adapters for
  dependency wiring.
- Adapters do not call one another directly. Cross-infrastructure workflows are
  coordinated by application use cases through ports.
- The OpenSearch adapter cannot call the LLM, and the model adapter cannot call
  OpenSearch, PostgreSQL, MinIO, Keycloak, or OpenFGA.
- The frontend imports generated or reviewed API contracts, not backend modules.
  Frontend route guards are user experience controls, never authorization.
- Tests may use fakes that implement ports. Security integration tests exercise
  real adapters and instrument all text-bearing boundaries.

Import-boundary enforcement must become a lint/test rule when code is created.
Any exception requires an ADR and cannot bypass an authorization-bearing type.

## 3. Shared contract types

The following Python-like declarations document the required shape. They are not
implementation code and intentionally omit framework or vendor types.

```python
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType, Protocol

TenantId = NewType("TenantId", str)
PrincipalId = NewType("PrincipalId", str)
ResourceId = NewType("ResourceId", str)
RevisionId = NewType("RevisionId", str)
ChunkId = NewType("ChunkId", str)
EvidenceId = NewType("EvidenceId", str)


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class PrincipalContext:
    principal_id: PrincipalId
    tenant_id: TenantId
    correlation_id: str


@dataclass(frozen=True)
class CandidateEnvelope:
    resource_id: ResourceId
    revision_id: RevisionId
    chunk_id: ChunkId
    tenant_id: TenantId
    lexical_score: float | None
    vector_score: float | None
    metadata: Mapping[str, str]


@dataclass(frozen=True)
class AuthorizedObjectId:
    resource_id: ResourceId
    revision_id: RevisionId
    tenant_id: TenantId
    decision_token: str


@dataclass(frozen=True)
class AuthorizedChunk:
    evidence_id: EvidenceId
    authorized_object: AuthorizedObjectId
    text: str
    metadata: Mapping[str, str]
```

`decision_token` is an opaque request-bound proof/reference, not a bearer token
accepted from clients. Its concrete representation is deferred. Serialization of
`AuthorizedObjectId` or `AuthorizedChunk` from API input is prohibited.

## 4. Required ports

### Connector

```python
class Connector(Protocol):
    source_type: str

    async def changes(
        self,
        *,
        tenant_id: TenantId,
        checkpoint: str | None,
    ) -> AsyncIterator["SourceEnvelope"]: ...
```

Contract: emits source revisions/deletions with stable IDs, cursor, provenance,
integrity metadata, timestamps, and source ACL inputs. It does not emit canonical
authorization grants from free-form content.

### Parser

```python
class Parser(Protocol):
    parser_version: str

    async def parse(self, raw: "RawObjectRef") -> "ParsedDocument": ...
```

Contract: accepts a validated raw-object reference, enforces supported media and
resource bounds, and returns structured elements or a typed failure. It has no
arbitrary network access.

### Chunker

```python
class Chunker(Protocol):
    chunker_version: str

    def chunk(self, document: "NormalizedDocument") -> Sequence["ChunkDraft"]: ...
```

Contract: deterministic for the same normalized revision and version; preserves
parent, ordinal, offsets, content hash, and security metadata references.

### Embedder

```python
class Embedder(Protocol):
    embedding_version: str

    async def embed(self, texts: Sequence[str]) -> "EmbeddingBatch": ...
```

Contract: configured local default, bounded batch, dimension/version validation,
and no user/role/relationship data encoded into the embedding.

### Search backend

```python
class SearchBackend(Protocol):
    async def hybrid_candidates(
        self,
        query: "HybridQuery",
        scope: "AuthorizationScope",
    ) -> Sequence[CandidateEnvelope]: ...

    async def fetch_authorized_chunks(
        self,
        ids: Sequence[AuthorizedObjectId],
    ) -> Sequence[AuthorizedChunk]: ...

    async def upsert(self, batch: "IndexBatch") -> "IndexReceipt": ...
    async def tombstone(self, resource: ResourceId) -> "DeletionReceipt": ...
```

Contract: server-generated scope is mandatory; client filters only narrow it.
Candidate search returns no text. Text fetch requires authorization-bearing IDs
and checks tenant/revision consistency.

### Authorization service

```python
class AuthorizationService(Protocol):
    async def resolve_scope(
        self,
        principal: PrincipalContext,
        action: str,
    ) -> "AuthorizationScope": ...

    async def check_view(
        self,
        principal: PrincipalContext,
        candidates: Sequence[CandidateEnvelope],
    ) -> Mapping[ChunkId, "AuthorizationDecision"]: ...

    async def check_share(
        self,
        principal: PrincipalContext,
        audience: "AudienceContext",
        claims: Sequence["EvidenceClaim"],
    ) -> Mapping[str, "ShareDecision"]: ...
```

Contract: OpenFGA-backed relationship truth plus deterministic lifecycle and
classification policy. Only explicit `ALLOW` creates an authorization-bearing
type. Unavailable or inconsistent state is `INDETERMINATE` and fails closed.

### Reranker

```python
class Reranker(Protocol):
    @property
    def reranker_version(self) -> str: ...

    def rerank(
        self,
        query: str,
        chunks: Sequence[AuthorizedChunk],
        *,
        limit: int,
        timeout_ms: int,
    ) -> Sequence["RerankScore"]: ...
```

Contract: configured local default; accepts authorized text only; cannot add
candidates or alter policy metadata. P13 treats unknown/duplicate returned IDs
as a safe fallback condition, never as new evidence.

### Evidence content store

```python
class EvidenceContentStore(Protocol):
    def load(
        self,
        candidates: Sequence[RetrievalCandidate],
    ) -> Sequence["EvidenceMaterial"]: ...
```

Contract: reads source text only for the application reauthorized candidate
subset and returns trusted lifecycle/authority/freshness metadata with it. It
cannot search, enumerate, accept client IDs, or grant access.

### LLM

```python
class LLM(Protocol):
    model_version: str

    async def generate(
        self,
        request: "GroundedGenerationRequest",
    ) -> "DraftAnswer": ...
```

Contract: configured local default; request contains system-owned instructions,
question, and immutable authorized evidence package only. Output is untrusted and
must pass deterministic validation.

### Evidence resolver

```python
class EvidenceResolver(Protocol):
    resolver_version: str

    def resolve(
        self,
        inputs: Sequence["EvidenceResolutionInput"],
    ) -> "EvidenceResolution": ...
```

Contract: deterministic authority, freshness, supersession, conflict, and
sufficiency result. It cannot fetch new content, interpret source text as
policy, or broaden authorization.

### Audit sink

```python
class AuditSink(Protocol):
    async def append(self, event: "AuditEvent") -> "AuditReceipt": ...
```

Contract: typed, minimized, redacted, correlated, durable security events. A
required-event failure follows the protected failure policy and is never silently
swallowed.

## 5. Supporting ports

The application also requires narrow ports for raw object storage, lifecycle
metadata, job/checkpoint leasing, cache invalidation, context construction,
citation validation, clock/ID generation, and telemetry. These ports follow the
same direction rules. Context construction accepts `EvidenceResolution`, not raw
search results; citation validation accepts the immutable evidence package and
draft answer; cache invalidation is required even while the initial cache is
request-local/no-op.

## 6. Frontend boundaries

React feature modules call a typed API client. Authentication state is obtained
through the local OIDC flow, held using the selected secure browser pattern, and
never converted into direct OpenFGA/OpenSearch access. The UI renders server
decisions, validated citations, policy warnings, and generic refusals. It does
not hide unauthorized content as an authorization mechanism and does not infer
shareability from classification labels.
