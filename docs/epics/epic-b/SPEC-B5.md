You are implementing Epic B / B5 for the AI Outbound Support Engine.

Task
Implement DB models + migration for Evidence and EvidenceContent only.

Source of truth
Treat these as authoritative and do not drift from them:
- AI-Outbound-Support-Engine-Data-Spine-v0.1(Updated).txt
- Epic-B-Contract-Lock.txt
- Project-Roadmap.txt
- Aose-Guardrails-&-Governance-(policy-Pack-Safe-V0-1).txt
- PLACEHOLDERS.md.txt

Ticket
B5. DB models: Evidence + EvidenceContent
Acceptance: evidence pointer saved with url + snippet + claim_frame

Scope boundary
IN SCOPE
- SQLAlchemy ORM models for Evidence and EvidenceContent
- Alembic migration(s)
- Minimal create/read tests for both models
- Deterministic evidence_id generation wired to existing Epic B ID helpers from B1
- Optional linkage from Evidence to EvidenceContent
- Pointer-first storage shape

OUT OF SCOPE
- No StructuredEvent table
- No Trace table
- No send logic
- No purge job
- No raw snapshot storage implementation
- No new canonical tables outside Evidence / EvidenceContent
- No speculative provider integrations
- No policy engine logic beyond storing required fields

Non-negotiable contract requirements
1. Use exact model/table names:
- Evidence -> table `evidence`
- EvidenceContent -> table `evidence_contents`

2. Evidence must support the canonical pointer-first shape from the Data Spine:
- evidence_id
- source_type
- canonical_url
- captured_at
- snippet
- claim_frame
- provenance / provenance_json
- optional content reference
- version field (`v`)

3. EvidenceContent must support the canonical deduped content shape:
- evidence_content_id
- content_hash
- kind
- text
- raw_ref (or equivalent raw_ref_kind/raw_ref_id nullable fields)
- captured_at
- version field (`v`)

4. Use the locked evidence ID contract exactly:
`evidence:<sha256(source_type|canonical_url|captured_at_iso|sha256(snippet_text_or_empty))>`

5. Preserve provider-derived field requirements where applicable:
- source_provider
- source_ref
- observed_at
- confidence
Confidence must be constrained to 0.0..1.0

6. EvidenceContent is optional. Evidence must be storable without EvidenceContent.
This is required because v0.1 allows pointer-only evidence.

7. Keep implementation replay-safe and deterministic.
Re-inserting the same evidence payload should not create logically duplicated evidence rows.

Implementation guidance
Use the existing project stack and style already established in Epic A / earlier Epic B tickets.

Design the models conservatively:
- `Evidence.evidence_id` should be the primary key
- `EvidenceContent.evidence_content_id` should be the primary key
- `Evidence.content_ref_id` may be nullable and should reference `evidence_contents.evidence_content_id`
- `EvidenceContent.content_hash` should be indexed and unique if that fits the existing dedupe approach
- `Evidence.canonical_url` should be stored as text, not a vendor-specific URL type
- `provenance` can be stored as JSON/JSONB
- `raw_ref` can be represented as nullable structured columns or JSON, but keep it minimal
- `v` should default to 1

Suggested minimum column set

Evidence
- evidence_id: string PK
- source_type: string not null
- canonical_url: text not null
- captured_at: timestamp not null
- snippet: text not null
- claim_frame: text not null
- source_provider: string not null
- source_ref: string not null
- observed_at: timestamp not null
- confidence: numeric/float not null with DB check 0.0 <= confidence <= 1.0
- provenance_json: json/jsonb not null
- content_ref_id: nullable FK to evidence_contents.evidence_content_id
- v: int not null default 1

EvidenceContent
- evidence_content_id: string PK
- content_hash: string not null
- kind: string not null
- text: text not null
- raw_ref_kind: nullable string
- raw_ref_id: nullable string
- captured_at: timestamp not null
- v: int not null default 1

Do not add extra “smart” fields unless they are required to satisfy the contract.

ID/helper requirements
- Reuse existing normalization/hash helpers from B1 if available
- If evidence ID helper does not yet exist, add it in the same deterministic style as B1 without changing prior contracts
- Use UTF-8 sha256 hex hashing
- Use the locked delimiter convention already used in Epic B contract
- Empty snippet must still hash deterministically

Migration requirements
Create an Alembic migration that:
- creates `evidence_contents`
- creates `evidence`
- adds PK/FK/check constraints
- adds appropriate indexes for likely read paths
Recommended indexes:
- evidence.canonical_url
- evidence.captured_at
- evidence.content_ref_id
- evidence_contents.content_hash

Test requirements
Add focused unit tests that prove:
1. Evidence ID generation is deterministic for the same input
2. Different snippet values produce different evidence IDs
3. Evidence can be saved with pointer-only fields and no EvidenceContent row
4. EvidenceContent can be saved and linked from Evidence
5. Confidence outside 0.0..1.0 is rejected
6. Create/read roundtrip preserves url + snippet + claim_frame
7. Replay of the same evidence_id does not create duplicate logical records

Acceptance target
A reviewer should be able to:
- run migrations successfully
- create an Evidence row with canonical_url + snippet + claim_frame
- optionally attach EvidenceContent
- query it back and verify the fields persist exactly

Important guardrails
- Do not invent new stage names, enums, or table names
- Do not create event logging tables; those are deferred to Epic C
- Do not implement purge/retention jobs yet
- Do not enable any external network behavior
- Keep the diff minimal and mergeable

Output format
Return:
1. Summary of files changed
2. Migration added
3. ORM models added/updated
4. Tests added
5. Any contract assumptions you had to preserve explicitly

Definition of done
Done means B5 acceptance is met exactly: evidence pointer saved with url + snippet + claim_frame, optional EvidenceContent exists, migration passes, and tests prove deterministic and replay-safe behavior.