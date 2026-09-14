# Grounded Generation And Citation Integrity

## Boundary

P14 begins only with a typed `EvidenceResolution` produced by P13. Its packets
already passed current `can_view` reauthorization before their text was loaded.
P13 derives one SHA-256 authorization binding from that reauthorization pass and
applies it to the resolution trace and every retained packet. The context
builder rejects a correlation or fingerprint mismatch before any model call.

The generation service does not accept raw search hits, chunks, client evidence
IDs, raw OpenSearch responses, or client ACL filters. It does not retrieve,
rerank, invoke tools, export data, or decide authorization/classification.

## Context Construction

`AuthorizedContextBuilder` selects packets in resolver order under independent,
deterministic limits: 12 evidence items, 12,000 characters per item, and
24,000 evidence characters total. An item that cannot fit is omitted; text is
never silently truncated. A conflict reaches the model only when every member
of that conflict is selected.

The local adapter sends four messages: a fixed trusted system prompt, the
bounded user question, a separately delimited `UNTRUSTED_EVIDENCE_DATA_JSON`
user message, and a trusted retry instruction only after citation validation
fails. Retrieved text is JSON-encoded solely in the data message, never the
system prompt. The prompt states that source instructions, policy changes,
secret requests, and action requests have no authority.

## Local Model Contract

`GroundedLLM` accepts only `AuthorizedGenerationContext` and returns a typed
`ModelDraft`. The default implementation is an Ollama-compatible local HTTP
adapter. Its endpoint must be loopback HTTP (`127.0.0.1`, `localhost`, or
`::1`) and cannot include credentials. It has no tool parameter, tool adapter,
or cloud endpoint path.

The model returns JSON with `insufficient_evidence` and bounded factual
`claims`. Every claim contains one or more `{evidence_id, quote}` proposals.
The configured model name, model artifact/version, timeout, output-token limit,
and concurrency limit are local configuration rather than business logic.

## Validation And Response

`CitationValidator` accepts a proposed citation only when its evidence ID is in
the selected context and its exact quote occurs in that packet's sanitized
text. A model cannot provide source URLs, titles, locators, classifications, or
authority metadata. `ValidatedCitation` maps those fields only from backend
`EvidencePacket` data.

An invalid citation triggers exactly one retry with the same context. A second
invalid draft returns the generic insufficient-accessible-evidence refusal.
No-evidence requests refuse without a model call. Local model timeout,
unavailability, malformed response, or exhausted concurrency returns a generic
unavailable response with no evidence-derived claims, conflicts, or
qualifications.

For a validated answer, conflict notices and stale/tentative/approved/committed
qualifications are derived by the backend from P13 metadata. They are not model
authority decisions. The future frontend must render answer and citation fields
as plain text and use backend citation metadata rather than source HTML.

## Trace

`GenerationTrace` is content-free and includes correlation ID, current
authorization fingerprint, prompt purpose/version/hash, model ID/version,
selected evidence IDs, context size, attempt count, citation-validation state,
final outcome, latency, and UTC timestamp. The mandatory trace sink port
receives this record before an answer is returned. Raw questions, evidence text,
model context, model response body, and local model error bodies are excluded.

The current phase supplies the typed trace/sink boundary. Wiring it to the
canonical durable query-trace store requires a dedicated schema design because
the P07 table does not yet expose the P14 prompt/model/citation fields.
