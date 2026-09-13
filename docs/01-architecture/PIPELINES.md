# Mandatory Pipelines

These pipelines are normative ordering contracts. Implementations may batch or
parallelize stages only when the same security boundaries, lifecycle outcomes,
and audit evidence are preserved.

## A. Ingestion pipeline

```text
connector -> raw store -> parse -> normalize -> ACL map -> classify -> chunk
          -> embed -> index -> checkpoint
```

1. **Connector** emits a typed source envelope with tenant, source identity,
   revision, timestamps, content locator, integrity metadata, and deletion state.
2. **Raw store** writes the original payload to a tenant-scoped MinIO location
   before parsing. The object receives an integrity hash and quarantine state.
3. **Parse** converts only supported, bounded file/content forms into structured
   elements. Parser failure is explicit; active or unsafe content is rejected.
4. **Normalize** maps source fields, timestamps, participants, account,
   department, provenance, revision, and lifecycle metadata into canonical form.
5. **ACL map** deterministically maps trusted source identities and relations to
   OpenFGA objects/relations. Source body text cannot create an authorization
   tuple.
6. **Classify** applies trusted source labels, administrator-approved mappings,
   or deterministic policy. No LLM performs security classification.
7. **Chunk** creates stable, lineage-bearing chunk drafts with content hashes,
   ordinals, parent revision, and policy metadata references.
8. **Embed** invokes the configured local embedding adapter with content only.
   Permission relationships are not encoded into vectors.
9. **Index** writes versioned OpenSearch documents containing searchable text,
   vector, lineage, tenant, lifecycle, and coarse filter metadata. OpenFGA remains
   relationship truth.
10. **Checkpoint** commits source cursor, revision, component versions, counts,
    and outcome in PostgreSQL only after the required raw, relation, metadata,
    and index writes are consistent. Partial failure is retryable and ineligible
    data remains unavailable.

Hourly synchronization schedules connector jobs, but checkpoints are based on
source cursors and revisions rather than wall-clock assumptions. Replay is
idempotent by tenant, source resource, revision, and pipeline version.

## B. Query pipeline

```text
authenticate -> resolve authorization scope
             -> permission-constrained hybrid retrieval -> rerank
             -> evidence resolution -> context construction -> LLM
             -> citation validation -> policy warning -> response
             -> audit trace
```

1. **Authenticate** validates the Keycloak OIDC token and creates a server-owned
   principal with a single tenant binding. Client tenant/role claims are not
   authorization grants.
2. **Resolve authorization scope** queries OpenFGA for current tenant, account,
   department, role, and explicit object relationships. A request-local
   `AuthorizationScope` carries the policy model/version and permitted coarse
   scopes.
3. **Permission-constrained hybrid retrieval** builds server-generated
   OpenSearch filters and intersects them with allowlisted user semantic filters.
   OpenSearch performs BM25 and vector retrieval but returns candidate envelopes
   without text. Each candidate is then fine-checked through OpenFGA.
4. **Authorized text fetch** is an internal substep of retrieval: only IDs with a
   current allow decision may load chunk text. A denied, missing, or uncertain
   decision is dropped and audited before reranking.
5. **Rerank** receives only `AuthorizedChunk` values and applies the configured
   local reranker. It cannot broaden the candidate set or alter authorization.
6. **Evidence resolution** applies deterministic source authority, effective
   time, supersession, conflict, and sufficiency rules to authorized chunks.
7. **Context construction** creates an immutable evidence package from resolved
   authorized evidence. Retrieved content is delimited as untrusted data and
   evidence IDs are server-issued.
8. **LLM** receives only the system-controlled task, user question, and authorized
   evidence package through the configured local adapter. It has no data-store,
   OpenFGA, export, or policy-changing credentials.
9. **Citation validation** accepts only evidence IDs and spans supplied in the
   package, and rejects unsupported claims or malformed model output.
10. **Policy warning** applies deterministic stale/conflict/insufficiency
    warnings and, for an external audience, evaluates `can_share_externally` for
    each evidence-derived claim. It may redact, qualify, require review, or
    refuse.
11. **Response** returns the validated answer, citations, warnings, and generic
    refusal/error shape without exposing denied resource existence.
12. **Audit trace** records minimized stage outcomes, versions, reason codes,
    authorized evidence IDs, and correlation data. It never records unauthorized
    text or complete model context by default.

The API must not call the reranker, context builder, or LLM when the authorized
evidence collection is empty. Retrieval fallbacks repeat the same scope and
fine-check contract.

## C. Deletion and permission-change pipeline

```text
detect -> remove/tombstone derivatives -> invalidate cache
       -> remove auth relation -> audit
```

1. **Detect** a source deletion, source de-permissioning event, operator-approved
   deletion, or authoritative reconciliation difference. PostgreSQL immediately
   marks the resource `deletion_pending`, which makes content fetch fail closed.
2. **Remove/tombstone derivatives** removes or tombstones OpenSearch chunks and
   vectors, marks canonical revisions deleted, and applies the configured MinIO
   retention/deletion policy. A tombstone prevents stale replay from resurrecting
   the resource.
3. **Invalidate cache** removes any query, evidence, citation, or shareability
   cache entries keyed to the resource/revision. The initial architecture has no
   cross-request result cache, but the invalidation port remains mandatory.
4. **Remove auth relation** deletes or replaces related OpenFGA tuples. Until
   completion, the PostgreSQL deletion state prevents text fetch even if a tuple
   or index derivative is temporarily stale.
5. **Audit** emits a lifecycle event with source event ID, resource/revision IDs,
   affected derivative counts, policy model/version, lag, outcome, and failures.

Retries are idempotent. Completion requires reconciliation proving no searchable
derivative, eligible citation, active cache key, or live relation remains. Raw
objects retained by an explicit legal/operations policy remain inaccessible to
query paths and are not searchable derivatives.

## D. Role and relationship change pipeline

```text
authorization relationship update -> next query resolves new scope
                                  -> no re-embedding
```

1. An identity/account/department administrator or source reconciliation job
   writes the validated relationship change to OpenFGA.
2. The change event records the resulting authorization model/tuple revision and
   invalidates any cross-request authorization scope cache. The initial design
   uses request-local scope only.
3. The next query resolves scope from current OpenFGA relationship truth and
   creates new server-generated search filters.
4. Candidate IDs receive a current fine check before text fetch. A stale coarse
   OpenSearch field cannot authorize content.
5. Existing content vectors remain unchanged because they encode content, not
   user or relationship permission.
6. A minimized audit event records the relationship change and the policy version
   observed by subsequent queries.

The role-change success criterion is security behavior on the next authorized
query, not completion of a reindex or re-embedding job.
