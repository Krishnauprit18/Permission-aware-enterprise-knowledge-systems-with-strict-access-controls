# Product Invariants

These are the product properties that later phases must preserve and test. P00 records them; it does not implement the product.

## Core workflow

An authenticated enterprise user asks a question over fragmented internal data. The system ingests at least three heterogeneous source types, parses and chunks content, attaches source/account/department/timestamp/access-level metadata, retrieves only authorized evidence, combines lexical and semantic retrieval, reranks candidates, resolves authority/freshness/conflicts, generates a grounded answer with validated citations, applies confidentiality/shareability policy, and emits an auditable trace.

## Security invariants

- An unauthorized chunk must not reach any LLM prompt, embedding request, reranker input, citation builder, or answer-generation context.
- Authorization is explicit, deterministic, deny-by-default, and evaluated for the authenticated principal and current permission state.
- `can_view` is distinct from `can_share_externally`; a user may view evidence without being allowed to share its contents.
- Revocation and deletion must affect retrieval behavior dynamically within a defined, tested bound.
- Source content is untrusted data. Prompt-injection text is data to contain, never an instruction to follow.
- Refuse or qualify answers when evidence is missing, stale, conflicting, insufficiently authoritative, or not shareable.

## Evaluation obligations

The project must maintain a golden dataset with at least 50 questions and report retrieval evaluation separately from generation evaluation. The dataset and tests must cover authorized and unauthorized users, refusals, conflicts, stale data, citation validity, dynamic role revocation, deletion, and source updates.
