# Parsing, Normalization, and Chunking

## Boundary

P10 is the bounded transformation between a P09 `SourceEnvelope` and future
embedding/indexing adapters. It consumes source bytes and canonical metadata;
it does not call a model, write OpenSearch, resolve authorization, or decide
whether a principal may view a resource. The envelope's tenant, classification,
shareability, account, department, timestamps, authority, version, and ACL
relationship references are copied to every emitted chunk.

The parser treats source bytes and all fields inside them as untrusted data.
Only the connector-selected source type controls the parser branch. Source
body text, headings, JSON values, macros, and retrieved instructions cannot
change authorization, classification policy, or system instructions.

## Source-aware parsing

| Source type | Parsing strategy | Citation locator |
|---|---|---|
| `document`, `policy`, `contract` | Markdown heading/section blocks; fenced code and tables remain grouped data | source ID, section path, line range |
| `slack_thread` | Parent and nested replies, bounded by thread depth; each message remains identifiable | channel, thread ID, message ID |
| `support_ticket` | Ticket metadata followed by comment blocks; comments are packed only into coherent bounded windows | ticket ID and comment ID |
| `call_transcript` | Speaker turns are grouped into bounded turn windows | call ID, speaker text, turn range |
| `hourly_feed` | Canonical sorted JSON record for the future update path | source ID |

Malformed JSON, missing required source-native fields, unsupported source types,
missing bodies, and resource-limit violations fail closed with a typed input
error. A deletion marker is handled by the P09 lifecycle path and is not parsed
as searchable content.

## Normalization and active content

Text is decoded as UTF-8 with replacement for malformed byte sequences and is
normalized to Unicode NFC. NUL and other non-printing controls are removed;
line endings are normalized to LF. Script/style/iframe/object/embed/SVG blocks,
HTML comments, and HTML tags are removed as data handling. No HTML, script,
macro, office active content, URL, attachment, or source instruction is
executed. Macro-looking text that is not active content remains ordinary text.

The normalizer preserves source wording, including indirect prompt-injection
strings, as untrusted evidence text. Later query code must label this text as
data and must never concatenate it into system instructions.

## Classification and metadata

Classification is deterministic and metadata-first. A valid canonical
`Classification` is preserved. Missing or unknown values default to
`RESTRICTED`, the conservative policy for content that cannot be safely
classified. `external_shareable` is retained only for `PUBLIC` or
`CUSTOMER_SHAREABLE` content; view permission and external sharing remain
separate decisions and are not inferred by this pipeline.

Every `ContentChunk` carries:

- parent `document_id` and stable `document_version_id`;
- tenant, source type/external ID, URL, account IDs, department, timestamps,
  author, language, authority, classification, and external-share flag;
- ACL relationship references for the later authorization boundary;
- normalized text, deterministic content hash, ordinal, token/line counts;
- one or more source locators suitable for citation reconstruction.

## Bounds and deterministic identity

The default limits are 2 MiB and 2,000,000 characters per document, 50,000
lines per document, 4,000 characters/800 lexical tokens/80 lines per chunk, and
eight nested Slack reply levels. These are configuration values, not grants;
callers may tighten them but may not bypass them. Transcript windows default to
eight turns.

Chunking first respects headings, paragraphs, tables, code blocks, messages,
comments, and transcript windows. It then greedily packs adjacent blocks while
all independent bounds hold. Oversized blocks fall back to line and word
boundaries, with a final bounded character split only for one unbreakable token.
Fixed-character splitting is therefore a last-resort safety bound, not the
chunking strategy.

The chunk ID is `stable_chunk_id(document_id, metadata.version, ordinal,
content_hash)`. Re-ingesting identical bytes at the same version produces the
same identity; a version or content change produces a different identity.
`ChunkingMetrics` records input bytes/chars/lines/tokens, empty blocks, split
blocks, and emitted chunk count without recording content.

## P10 non-goals

No embedding model, tokenizer-specific budget, OpenSearch mapping, cache,
retrieval filter, reranker, evidence resolver, citation validator, or LLM is
implemented here. The lexical token counter is a deterministic pre-index bound;
the later embedding/index adapter must enforce its own model-specific limits.
