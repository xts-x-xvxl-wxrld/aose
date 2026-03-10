You are implementing Epic B / B9 for the AI Outbound Support Engine.

Task
Implement DB models + migration for ApprovalDecision and SendAttempt only.

Source of truth
Treat these as authoritative and do not drift from them:
- AI-Outbound-Support-Engine-Data-Spine-v0.1(Updated).txt
- Epic-B-Contract-Lock.txt
- Project-Roadmap.txt
- Aose-Guardrails-&-Governance-(policy-Pack-Safe-V0-1).txt
- PLACEHOLDERS.md.txt

Ticket
B9. DB models: ApprovalDecision + SendAttempt
Acceptance: approval state transition recorded; send attempts are idempotent by key

Scope boundary
IN SCOPE
- SQLAlchemy ORM models for ApprovalDecision and SendAttempt
- Alembic migration(s)
- Minimal create/read tests
- Deterministic decision_key generation
- Deterministic decision_id / send_id / send idempotency key wiring from existing Epic B ID helpers where applicable
- Uniqueness constraints that enforce replay safety for human decision records and send-attempt side effects
- Storage of policy-carry fields required by the policy pack

OUT OF SCOPE
- No actual sending implementation
- No provider enqueue/poll integration
- No approval UI
- No workflow engine changes
- No rate limiting logic
- No suppression engine logic
- No auto-creation of SendAttempt when send is disabled
- No new event/trace tables
- No speculative delivery-status state machine beyond minimal storage

Non-negotiable contract requirements
1. Use exact model/table names:
- ApprovalDecision -> table `approval_decisions`
- SendAttempt -> table `send_attempts`

2. Preserve the canonical ApprovalDecision shape from the Data Spine, at minimum:
- decision_id
- draft_id
- status
- reviewer
- notes
- decided_at
- v

3. Preserve the policy-pack carry fields for ApprovalDecision:
- decision_key
- reviewer_id
- reviewer_role
- overridden_gates[]
- policy_pack_id

4. Preserve the canonical SendAttempt shape from the Data Spine, at minimum:
- send_id
- draft_id
- channel
- provider
- status
- provider_message_id
- idempotency_key
- created_at
- v

5. Preserve the policy-pack carry fields for SendAttempt:
- provider enum
- policy_pack_id

6. Use the locked deterministic formulas exactly:
- decision_key = `sha256(work_item_id|contact_id|action_type|policy_pack_id|draft_id)`
- decision_id = `decision:<draft_id>:<decision_key>`
- send_id = `send:<draft_id>:<channel>`
- send_idempotency_key = `send:<draft_id>:<channel>:v1`

7. Use the locked approval statuses exactly:
- `approved`
- `rejected`
- `needs_rewrite`
- `needs_more_evidence`

8. SendAttempt idempotency must be enforced by storage uniqueness on `idempotency_key`.

9. Keep implementation replay-safe and deterministic.
Re-inserting the same decision or send attempt must not create unintended duplicate logical records.

Important contract conflict to resolve explicitly
The policy pack describes human/event-like decision records as generated IDs reused via decision_key lookup.
For B9, the Epic-B-Contract-Lock is authoritative for the actual deterministic `decision_id` formula:
- `decision:<draft_id>:<decision_key>`

Do not invent a UUID/ULID-based decision_id in this ticket.

Second important constraint
The policy pack also states:
- `send_enabled=false => no SendAttempt created`

For B9, implement storage only.
This means:
- build the `send_attempts` table and replay-safe uniqueness
- do not add runtime logic that auto-creates SendAttempt rows
- do not add any real send-side effect code
- tests may verify persistence and idempotency behavior at the model/DB level only

Implementation guidance
Use the existing project stack and style already established in Epic A / prior Epic B tickets.

Model design should stay conservative.

Recommended minimum ApprovalDecision columns
- decision_id: string PK
- decision_key: string not null unique
- draft_id: string not null FK to `outreach_drafts.draft_id`
- work_item_id: string not null FK to `work_items.work_item_id` if WorkItem exists in current repo
- contact_id: string not null FK to `contacts.contact_id`
- action_type: string not null
- status: string not null
- reviewer: string nullable
- reviewer_id: string not null
- reviewer_role: string not null
- notes: text nullable
- overridden_gates_json: json/jsonb not null default `[]`
- policy_pack_id: string not null
- decided_at: timestamp not null
- v: int not null default 1

Recommended minimum SendAttempt columns
- send_id: string PK
- draft_id: string not null FK to `outreach_drafts.draft_id`
- decision_id: string nullable or not null FK to `approval_decisions.decision_id`
- channel: string not null
- provider: string not null
- status: string not null
- provider_message_id: string nullable
- idempotency_key: string not null unique
- policy_pack_id: string not null
- created_at: timestamp not null
- v: int not null default 1

Schema notes
- `decision_id` should be deterministic from `draft_id` + `decision_key`
- `decision_key` uniqueness is the replay protection for decisions
- `idempotency_key` uniqueness is the replay protection for send attempts
- `decision_id` may be enough as PK, but still keep `decision_key` as a separate unique column because the policy pack explicitly requires it
- Prefer JSON/JSONB for `overridden_gates_json`
- `policy_pack_id` should default to `safe_v0_1` only if that matches current repo conventions; otherwise require explicit value

Validation requirements
ApprovalDecision:
- `draft_id` required
- `work_item_id` required if used by the locked decision_key formula
- `contact_id` required if used by the locked decision_key formula
- `action_type` required
- `status` must be one of the exact locked approval statuses
- `reviewer_id` required
- `reviewer_role` required
- `overridden_gates_json` must be an array
- `policy_pack_id` required
- `decided_at` required

SendAttempt:
- `draft_id` required
- `channel` required
- `provider` required
- `idempotency_key` required
- `policy_pack_id` required
- `created_at` required
- `provider` should be constrained to the locked provider enum currently available in Epic B:
  - `SEND_SRC_01`
- do not invent a broad provider enum set unless it already exists in the repo
- `status` is required, but do not over-specify a large enum if the contract has not locked one
- tests should use minimal known values such as `queued`

Decision action type
The decision_key formula depends on `action_type`, but the contract does not lock a large enum for it here.
Therefore:
- if an action_type enum/helper already exists in the repo, reuse it exactly
- otherwise use the narrowest conservative value needed for B9 tests, for example `approve_send`
- document that assumption in your output
- do not redesign a global action taxonomy in this ticket

Reviewer fields
The Data Spine example uses a single `reviewer` string.
The policy pack additionally requires:
- `reviewer_id`
- `reviewer_role`

Store all of them.
A conservative mapping is:
- `reviewer` = display form like `human:TBD`
- `reviewer_id` = stable reviewer identity
- `reviewer_role` = role such as `operator` or `admin`

Suggested indexes
ApprovalDecision:
- unique index on `decision_key`
- index on `draft_id`
- index on `contact_id`
- index on `decided_at`
- optionally index on `status`

SendAttempt:
- unique index on `idempotency_key`
- index on `draft_id`
- index on `decision_id`
- index on `created_at`
- optionally index on `(draft_id, channel)`

Replay-safety guidance
- identical decision inputs must produce the same `decision_key`
- the same `decision_key` must not create duplicate decision rows
- the same `(draft_id, channel)` must deterministically produce the same `send_id`
- the same send idempotency input must not create duplicate send-attempt rows
- do not rely on auto-increment for any deterministic identifier in this ticket

Migration requirements
Create an Alembic migration that:
- creates `approval_decisions`
- creates `send_attempts`
- adds PK/FK constraints
- adds unique constraints for `decision_key` and `idempotency_key`
- adds useful indexes
- keeps the schema minimal and mergeable

Test requirements
Add focused tests that prove:
1. An ApprovalDecision can be saved and read back
2. `decision_key` generation is deterministic for the same inputs
3. `decision_id` generation follows the exact locked formula
4. ApprovalDecision status rejects values outside the locked set
5. `overridden_gates_json` roundtrips as an array
6. Replay of the same decision payload does not create unintended duplicate decision rows
7. A SendAttempt can be saved and read back
8. `send_id` generation follows the exact locked formula
9. `idempotency_key` generation follows the exact locked formula
10. Replay of the same send-attempt payload is blocked by unique `idempotency_key`
11. Provider rejects values outside the locked provider enum if enum validation is implemented
12. No real provider/network side effects occur anywhere in tests or implementation

Acceptance target
A reviewer should be able to:
- run migrations successfully
- create an ApprovalDecision for a draft and verify the approval state transition is recorded
- create a SendAttempt row manually at the storage layer and verify replay is blocked by idempotency key
- query both records back and verify fields persist exactly

Guardrails
- Do not invent a UUID/ULID decision_id
- Do not invent a different send_id or send idempotency formula
- Do not add provider integrations
- Do not add runtime logic that bypasses `send_enabled=false`
- Do not create event logging or trace tables
- Keep the diff minimal and mergeable

Output format
Return:
1. Summary of files changed
2. Migration added
3. ORM models added/updated
4. Tests added
5. Any `action_type` assumption you had to preserve explicitly
6. Any choice about `decision_id` / `decision_key` conflict handling you preserved explicitly

Definition of done
Done means B9 acceptance is met exactly: approval state transition recorded; send attempts are idempotent by key; migration passes; tests prove deterministic and replay-safe storage behavior; no real send-side effects exist.