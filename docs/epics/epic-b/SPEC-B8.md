You are implementing Epic B / B8 for the AI Outbound Support Engine.

Task
Implement DB models + migration for OutreachDraft and PersonalizationAnchor only.

Source of truth
Treat these as authoritative and do not drift from them:
- AI-Outbound-Support-Engine-Data-Spine-v0.1(Updated).txt
- Epic-B-Contract-Lock.txt
- Project-Roadmap.txt
- Aose-Guardrails-&-Governance-(policy-Pack-Safe-V0-1).txt
- PLACEHOLDERS.md.txt

Ticket
B8. DB models: OutreachDraft + PersonalizationAnchors
Acceptance: draft stored, anchors map sentences → evidence IDs

Scope boundary
IN SCOPE
- SQLAlchemy ORM models for OutreachDraft and PersonalizationAnchor
- Alembic migration(s)
- Minimal create/read tests
- Deterministic draft_id generation wired to existing Epic B ID helpers from B1
- Separate anchor table for sentence/span → evidence linkage
- Conservative replay-safe behavior for drafts and anchors

OUT OF SCOPE
- No copy generator logic
- No template engine
- No approval workflow
- No sending logic
- No UI work
- No policy engine execution beyond storing required fields
- No speculative HTML rendering pipeline
- No new canonical tables outside OutreachDraft / PersonalizationAnchor

Non-negotiable contract requirements
1. Use exact model/table names:
- OutreachDraft -> table `outreach_drafts`
- PersonalizationAnchor -> table `personalization_anchors`

2. Preserve the canonical OutreachDraft shape from the Data Spine, at minimum:
- draft_id
- contact_id
- account_id
- channel
- language
- subject
- body
- risk_flags
- created_at
- v

3. Preserve the anchor linkage rule exactly:
Every personalization anchor maps a text span to one or more evidence_ids.

4. Use the locked draft ID contract exactly:
`draft:<contact_id>:seq<sequence_no>:v<variant_no>`

5. sequence_no and variant_no must come from deterministic stage inputs.
Do not use DB auto-increment to decide draft identity.

6. Keep anchors in a separate table for B8.
Do not collapse them into a single JSON blob on OutreachDraft.

7. Keep implementation replay-safe and deterministic.
Re-inserting the same logical draft payload should not create unintended duplicates.

Important contract resolution
The policy pack contains a broader hash-style note for draft identity.
For B8, the Epic-B-Contract-Lock is authoritative for the actual `draft_id` formula.
Do not invent or substitute a different draft_id strategy in this ticket.

Implementation guidance
Use the existing project stack and style already established in Epic A / prior Epic B tickets.

Model design should stay conservative.

Recommended minimum OutreachDraft columns
- draft_id: string PK
- contact_id: string not null FK to `contacts.contact_id`
- account_id: string not null FK to `accounts.account_id`
- channel: string not null
- language: string not null
- subject: text not null
- body: text not null
- risk_flags_json: json/jsonb not null
- created_at: timestamp not null
- v: int not null default 1

Recommended minimum PersonalizationAnchor columns
- anchor_key: string PK or unique deterministic key
- draft_id: string not null FK to `outreach_drafts.draft_id`
- span: text not null
- evidence_ids_json: json/jsonb not null
- v: int not null default 1

Anchor key requirement
The contract does not define a canonical anchor ID formula.
Therefore:
- If an anchor helper already exists in the repo, reuse it exactly.
- Otherwise implement the narrowest deterministic key, for example a hash of `draft_id|span|sorted_evidence_ids`, and document that assumption in your output.
- Do not redesign the global ID strategy.

Validation requirements
- `contact_id` is required
- `account_id` is required
- `channel` is required
- `language` is required
- `subject` is required; allow empty string only if the existing repo/channel rules explicitly support it
- `body` is required
- `risk_flags_json` must be an array, default `[]`
- `evidence_ids_json` must be an array
- every anchor must have at least one evidence ID
- `span` must be non-empty
- anchors must belong to exactly one draft
- if your model supports only known channels in v0.1 tests, use `email` and `linkedin`
- do not introduce approval-status or send-status columns here

Anchor semantics
Each anchor row should represent one text span in the draft and the evidence IDs backing that span.

Example shape to preserve semantically:
- span: "noticed you run SMT assembly"
- evidence_ids_json: ["evidence:9b2f1c..."]

Schema design preference
Keep anchor evidence links as JSON/JSONB array on `personalization_anchors`.
Do not create an additional join table unless the repo already has a strong established pattern for JSON avoidance.

Suggested indexes
OutreachDraft:
- index on `contact_id`
- index on `account_id`
- index on `created_at`

PersonalizationAnchor:
- index on `draft_id`
- if using deterministic uniqueness rather than PK-only, add a unique constraint on the chosen anchor identity rule

Replay-safety guidance
- `draft_id` must be deterministic from `contact_id`, `sequence_no`, and `variant_no`
- inserting the same draft again should not create a second logical draft row
- inserting the same anchor again should not create a second logical anchor row under the same draft

Migration requirements
Create an Alembic migration that:
- creates `outreach_drafts`
- creates `personalization_anchors`
- adds PK/FK constraints
- adds useful indexes
- keeps the schema minimal and mergeable

Test requirements
Add focused tests that prove:
1. An OutreachDraft can be saved and read back
2. `draft_id` generation follows the exact locked formula
3. The same deterministic inputs produce the same `draft_id`
4. Different sequence_no values produce different `draft_id` values
5. Different variant_no values produce different `draft_id` values
6. A PersonalizationAnchor can be saved and linked to a draft
7. Anchor roundtrip preserves `span` and `evidence_ids`
8. Anchor rows require at least one evidence ID
9. Replay of the same draft payload does not create unintended duplicate draft rows
10. Replay of the same anchor payload does not create unintended duplicate anchor rows
11. `risk_flags_json` defaults to an empty array and roundtrips correctly

Acceptance target
A reviewer should be able to:
- run migrations successfully
- create an outreach draft for a contact/account
- store one or more personalization anchors for that draft
- query the draft and verify anchors map text spans to evidence IDs exactly

Guardrails
- Do not invent a different draft_id formula
- Do not move anchors into ApprovalDecision or Evidence tables
- Do not add generator logic, approval logic, or send logic
- Do not add speculative HTML/email rendering fields unless already required by the repo’s established pattern
- Keep the diff minimal and mergeable

Output format
Return:
1. Summary of files changed
2. Migration added
3. ORM models added/updated
4. Tests added
5. Any anchor key assumption you had to preserve explicitly

Definition of done
Done means B8 acceptance is met exactly: draft stored, anchors map sentences/spans to evidence IDs, migration passes, and tests prove deterministic storage behavior.