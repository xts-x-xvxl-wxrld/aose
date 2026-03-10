You are implementing Epic B / B7 for the AI Outbound Support Engine.

Task
Implement DB models + migration for Contact and ContactAlias only.

Source of truth
Treat these as authoritative and do not drift from them:
- AI-Outbound-Support-Engine-Data-Spine-v0.1(Updated).txt
- Epic-B-Contract-Lock.txt
- Project-Roadmap.txt
- Aose-Guardrails-&-Governance-(policy-Pack-Safe-V0-1).txt
- PLACEHOLDERS.md.txt

Ticket
B7. DB models: Contact + ContactAlias
Acceptance: can store contact with email or linkedin fallback

Scope boundary
IN SCOPE
- SQLAlchemy ORM models for Contact and ContactAlias
- Alembic migration(s)
- Minimal create/read tests
- Deterministic contact_id generation wired to existing Epic B ID helpers from B1
- Alias storage for normalized email and normalized LinkedIn URL
- Replay-safe insert behavior for canonical contact identity

OUT OF SCOPE
- No enrichment pipeline
- No score thresholding or candidate→target promotion logic
- No send logic
- No Draft / Approval / Send models
- No mailbox verification provider integration
- No contact merge workflow beyond deterministic identity storage
- No speculative third fallback identity

Non-negotiable contract requirements
1. Use exact model/table names:
- Contact -> table `contacts`
- ContactAlias -> table `contact_aliases`

2. Use the locked contact ID precedence exactly:
- `contact:<account_id>:<normalized_email>`
- fallback `contact:<account_id>:<sha256(normalized_linkedin_url)>`

3. No third fallback in Epic B.
If both normalized email and normalized LinkedIn URL are missing, do not create a canonical Contact.

4. ContactAlias alias types must match the locked enum pack exactly:
- `email_normalized`
- `linkedin_url_normalized`

5. Preserve the canonical contact shape from the Data Spine, at minimum:
- contact_id
- account_id
- full_name
- role
- channels
- provenance
- status
- v

6. Channel validation must remain explicit-level, not boolean.

7. Reuse the locked normalization rules:
- email normalization from B1 / contract
- linkedin_url normalization from B1 / contract

8. Keep implementation replay-safe and deterministic.
Re-inserting the same canonical identity should not create logically duplicated contacts or alias rows.

Implementation guidance
Use the existing project stack and style already established in Epic A / prior Epic B tickets.

Model design should stay conservative.

Recommended minimum Contact columns
- contact_id: string PK
- account_id: string not null FK to `accounts.account_id`
- full_name: string/text nullable
- role_json: json/jsonb nullable
- channels_json: json/jsonb not null
- provenance_json: json/jsonb not null
- status: string not null default `candidate`
- v: int not null default 1

Recommended minimum ContactAlias columns
- account_id: string not null
- contact_id: string not null FK to `contacts.contact_id`
- alias_type: string not null
- alias_value: string not null
- v: int not null default 1

Schema notes
- Prefer not to invent a separate alias_id unless the repo already has a strong convention for it
- Add a uniqueness rule that prevents replay duplicates for alias rows
- The narrowest useful uniqueness rule is likely `(account_id, alias_type, alias_value)`
- Add an index on `contact_id`
- Add an index on `account_id`
- Add an index on `(account_id, alias_type, alias_value)`

Contact JSON shapes
Role JSON should stay close to the Data Spine:
{
  "cluster": "economic_buyer",
  "title": "Head of Production",
  "confidence": 0.66
}

Channels JSON should stay close to the Data Spine:
[
  {
    "type": "email",
    "value": "john.doe@example.si",
    "validated": "domain_ok",
    "validated_at": "2026-02-25T10:29:10Z",
    "source_trace": ["adapter:people_search_a"]
  },
  {
    "type": "linkedin",
    "value": "https://www.linkedin.com/in/john-doe",
    "validated": "profile_exists",
    "validated_at": "2026-02-25T10:29:10Z",
    "source_trace": ["adapter:people_search_a"]
  }
]

Provenance JSON should stay close to the Data Spine:
[
  {
    "adapter": "people_search_a",
    "captured_at": "2026-02-25T10:28:00Z"
  }
]

Validation requirements
- `account_id` is required
- at least one canonical identity input must exist after normalization:
  - normalized email, or
  - normalized LinkedIn URL
- if normalized email exists, it must win for contact_id generation
- if normalized email is absent and normalized LinkedIn URL exists, use the LinkedIn hash fallback
- if both are absent, reject contact creation
- `channels_json` must be an array
- `provenance_json` must be an array
- `status` should default to `candidate`
- if role confidence is present, constrain or validate it to 0.0..1.0
- email channel validation values must be restricted to the locked levels:
  - `unverified`
  - `syntax_ok`
  - `domain_ok`
  - `provider_verified`
  - `human_verified`
- linkedin channel validation values must be restricted to the locked levels:
  - `unverified`
  - `profile_exists`
  - `human_verified`

Alias behavior
- If email exists, store a ContactAlias row with:
  - alias_type = `email_normalized`
  - alias_value = normalized email
- If LinkedIn exists, store a ContactAlias row with:
  - alias_type = `linkedin_url_normalized`
  - alias_value = normalized LinkedIn URL
- If both exist, store both alias rows
- Alias rows are identity aids; they must not change the email-first contact_id precedence rule

Migration requirements
Create an Alembic migration that:
- creates `contacts`
- creates `contact_aliases`
- adds PK/FK constraints
- adds useful indexes
- adds uniqueness protection for alias replay
- keeps the schema minimal and mergeable

Test requirements
Add focused tests that prove:
1. A contact with email stores successfully
2. A contact with email generates the canonical email-based contact_id
3. A contact with no email but with LinkedIn stores successfully
4. A contact with no email but with LinkedIn generates the fallback hashed LinkedIn contact_id
5. A contact with both email and LinkedIn still uses email-first contact_id precedence
6. A contact with neither email nor LinkedIn is rejected
7. Email alias row is stored when email exists
8. LinkedIn alias row is stored when LinkedIn exists
9. Replay of the same alias payload does not create duplicate alias rows
10. Create/read roundtrip preserves channels and validation state
11. Invalid validation level values are rejected

Acceptance target
A reviewer should be able to:
- run migrations successfully
- create a canonical contact under an account using normalized email
- create a canonical contact under an account using LinkedIn fallback when email is absent
- query alias rows and verify normalized identity storage works

Guardrails
- Do not invent a third contact identity fallback
- Do not add enrichment or provider API logic
- Do not implement candidate promotion or send policy logic
- Do not leak into OutreachDraft, ApprovalDecision, or SendAttempt
- Keep the diff minimal and mergeable

Output format
Return:
1. Summary of files changed
2. Migration added
3. ORM models added/updated
4. Tests added
5. Any contact_id or alias uniqueness assumptions you had to preserve explicitly

Definition of done
Done means B7 acceptance is met exactly: a contact can be stored with email or LinkedIn fallback, alias storage works, migration passes, and tests prove deterministic identity behavior.