You are implementing Epic B / B6 for the AI Outbound Support Engine.

Task
Implement DB model + migration for Scorecard only.

Source of truth
Treat these as authoritative and do not drift from them:
- AI-Outbound-Support-Engine-Data-Spine-v0.1(Updated).txt
- Epic-B-Contract-Lock.txt
- Project-Roadmap.txt
- Aose-Guardrails-&-Governance-(policy-Pack-Safe-V0-1).txt
- PLACEHOLDERS.md.txt

Ticket
B6. DB models: Scorecard
Acceptance: fit+intent stored, reasons link to evidence IDs

Scope boundary
IN SCOPE
- SQLAlchemy ORM model for Scorecard
- Alembic migration(s)
- Minimal create/read tests
- Storage for fit and intent as separate scored sections
- Storage for reason objects where each reason has text + evidence_ids
- Conservative replay-safe behavior

OUT OF SCOPE
- No scoring engine
- No thresholding / promotion workflow
- No WorkItem orchestration changes
- No Draft / Approval / Send models
- No new reason table unless absolutely required by the current repo pattern
- No policy decision logic beyond storing required fields
- No speculative provider integrations

Non-negotiable contract requirements
1. Use exact model/table name:
- Scorecard -> table `scorecards`

2. Preserve the canonical scorecard shape from the Data Spine:
- scorecard_id
- entity_ref
- fit { score, confidence, reasons[] }
- intent { score, confidence, reasons[] }
- computed_at
- v

3. Fit and intent must remain separate.
Do not collapse them into one overall score.

4. Every reason object must store:
- text
- evidence_ids
This is locked in the Epic B contract.

5. Confidence values must be constrained to 0.0..1.0.
Apply the same to score values if the repo’s current convention treats fit/intent as normalized 0..1 floats.

6. Scorecard must link to the canonical entity reference:
- entity_ref_type
- entity_ref_id
For B6, assume the main target is `account`, but keep the schema generic enough to store the canonical entity ref pair.

7. Keep the implementation replay-safe and deterministic.
Do not silently create multiple logically identical scorecards for the same exact scoring snapshot unless the repo already has a deliberate versioning pattern.

Important ambiguity to handle explicitly
The docs are aligned on scorecard shape, but not perfectly aligned on one explicit scorecard_id formula.
Therefore:
- If a scorecard ID helper already exists in the repo, reuse it exactly.
- If none exists, implement the narrowest deterministic helper consistent with current project conventions and document that assumption in your output.
- Do not redesign global ID strategy in this ticket.

Implementation guidance
Use the existing project stack and style already established in Epic A / prior Epic B tickets.

Prefer a conservative schema. Recommended minimum columns:

Scorecard
- scorecard_id: string PK
- entity_ref_type: string not null
- entity_ref_id: string not null
- fit_score: numeric/float not null
- fit_confidence: numeric/float not null
- fit_reasons_json: json/jsonb not null
- intent_score: numeric/float not null
- intent_confidence: numeric/float not null
- intent_reasons_json: json/jsonb not null
- computed_at: timestamp not null
- v: int not null default 1

Reason JSON shape
Each reason object must look like:
{
  "text": "Matches EMS segment",
  "evidence_ids": ["evidence:..."]
}

Validation requirements
- fit_reasons_json and intent_reasons_json must always be arrays
- every reason must include `text`
- every reason must include `evidence_ids`
- `evidence_ids` must be an array, possibly empty
- score/confidence values outside allowed range must be rejected either at model validation, DB constraint level, or both
- do not allow null reasons payloads

Schema design preference
Unless the repo already uses a normalized side table pattern, keep fit/intent reasons in JSON/JSONB on the `scorecards` row.
This matches the current contract more directly and keeps B6 narrow.

Suggested indexes
- index on entity_ref_type, entity_ref_id
- index on computed_at
- if your replay-safe approach depends on a uniqueness rule, add the narrowest useful unique constraint and explain it

Migration requirements
Create an Alembic migration that:
- creates `scorecards`
- adds PK
- adds range checks for confidence fields
- adds range checks for score fields if normalized 0..1 is used
- adds indexes for expected read paths

Test requirements
Add focused tests that prove:
1. A scorecard can be saved and read back
2. Fit and intent are stored separately
3. Fit reasons preserve text + evidence_ids
4. Intent reasons preserve text + evidence_ids
5. Confidence outside 0.0..1.0 is rejected
6. Score outside allowed range is rejected if normalized score checks are implemented
7. Empty evidence_ids arrays are allowed for reasons
8. Reason objects missing `text` or `evidence_ids` are rejected
9. Replay of the same scoring payload does not create unintended duplicate logical records under your chosen uniqueness strategy

Acceptance target
A reviewer should be able to:
- run migrations successfully
- create a scorecard row for an entity
- store fit and intent independently
- store reasons that link to evidence IDs
- query it back and verify the values persist exactly

Guardrails
- Do not invent new table names
- Do not add scoring business logic
- Do not merge fit and intent
- Do not leak into Contact, Draft, Approval, or Send work
- Keep the diff minimal and mergeable

Output format
Return:
1. Summary of files changed
2. Migration added
3. ORM model added/updated
4. Tests added
5. Any scorecard_id assumption you had to preserve explicitly

Definition of done
Done means B6 acceptance is met exactly: fit+intent stored, reasons link to evidence IDs, migration passes, and tests prove the storage contract works.