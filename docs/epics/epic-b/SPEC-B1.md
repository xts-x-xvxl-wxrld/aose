Task: Execute Epic B1 only — implement canonical ID helpers and normalization helpers.

You are working inside the AOSE repo. Follow the locked Epic B contract exactly. Do not implement later tickets. Do not invent alternate ID formats, fallback chains, table names, or enum values.

Authoritative sources for this ticket:
1. Epic-B-Contract-Lock.txt
2. AI-Outbound-Support-Engine-Data-Spine-v0.1(Updated).txt
3. Project-Roadmap.txt

Scope for B1 only
Implement a small, deterministic ID/normalization module plus unit tests.

Required outcome
Create or update an `id.py`-style module that contains:
- normalization helpers
- canonical ID builders
- deterministic hash helper(s)

Also add unit tests that prove deterministic outputs and exact fallback precedence.

Hard boundaries
- Do NOT add DB models
- Do NOT add Alembic migrations
- Do NOT add queue logic
- Do NOT add structured events
- Do NOT implement merges beyond deterministic ID generation
- Do NOT “improve” the contract with your own naming
- Do NOT remove or alter existing behavior outside what is required for B1
- Keep diffs minimal and mergeable

Contract rules you must implement exactly

1) Hashing
- hash function: sha256 hex digest over UTF-8 bytes
- join delimiter for composite hashed inputs: "|"

2) Domain normalization
Implement a helper equivalent to:
`normalize_domain(value: str | None) -> str | None`

Rules:
- trim whitespace
- if input is a URL, parse host and discard scheme/path/query/fragment
- lowercase
- remove port
- remove trailing dot
- strip exactly one leading "www."
- convert host to IDNA ASCII
- if result is empty or invalid, return None

Examples of intended behavior:
- " Example.COM " -> "example.com"
- "https://www.Example.com/path?q=1" -> "example.com"
- "bücher.de" -> IDNA ASCII normalized host
- "example.com:443" -> "example.com"
- "" or invalid -> None

3) Email normalization
Implement:
`normalize_email(value: str | None) -> str | None`

Rules:
- trim whitespace
- split on "@"; invalid split => None
- lowercase local part
- normalize domain using domain normalization
- rejoin as "<local>@<normalized_domain>"
- do NOT remove plus-tags
- do NOT remove dots
- invalid result => None

Examples:
- " John.Doe+Ops@Example.COM " -> "john.doe+ops@example.com"
- "bad-email" -> None

4) LinkedIn URL normalization
Implement:
`normalize_linkedin_url(value: str | None) -> str | None`

Rules:
- trim whitespace
- lowercase scheme and host
- remove query string and fragment
- remove trailing slash
- keep path as the identity-bearing component
- invalid result => None

Examples:
- "https://www.linkedin.com/in/John-Doe/?trk=abc" -> normalized stable URL without query/fragment/trailing slash
- invalid input -> None

5) Canonical ID builders
Implement deterministic helpers for all locked Epic B identifiers.

Required helpers:
- `make_seller_id(seller_slug: str) -> str`
- `make_account_id(country: str | None, registry_id: str | None, domain: str | None, legal_name_normalized: str | None, source_provider: str | None, source_ref: str | None) -> str`
- `make_contact_id(account_id: str, email: str | None = None, linkedin_url: str | None = None) -> str`
- `make_evidence_id(source_type: str, canonical_url: str, captured_at_iso: str, snippet_text: str | None) -> str`
- `make_draft_id(contact_id: str, sequence_no: int, variant_no: int) -> str`
- `make_decision_key(work_item_id: str, contact_id: str, action_type: str, policy_pack_id: str, draft_id: str) -> str`
- `make_decision_id(draft_id: str, decision_key: str) -> str`
- `make_send_id(draft_id: str, channel: str) -> str`
- `make_send_idempotency_key(draft_id: str, channel: str) -> str`

Use the exact formulas below.

5a) Seller ID
Formula:
- `seller:<seller_slug>`

5b) Account ID
Fallback precedence is locked and must be exact:
1. `account:<COUNTRY>-<REGISTRY_ID>`
2. `account:<normalized_domain>`
3. `account:tmp:<sha256(country|legal_name_normalized|source_provider|source_ref)>`

Rules:
- use registry-based ID whenever country and registry_id both exist
- use domain-based ID only when registry ID is absent
- use tmp hash only when both registry ID and normalized domain are absent
- country must be uppercase ISO-like code
- registry_id must be stored in normalized string form exactly as emitted by your helper logic
- the tmp hash input must use the locked delimiter "|"

You may create a tiny helper for registry ID normalization if needed, but do not invent country-specific logic.

5c) Contact ID
Fallback precedence is locked and must be exact:
1. `contact:<account_id>:<normalized_email>`
2. `contact:<account_id>:<sha256(normalized_linkedin_url)>`

Rules:
- no third fallback in Epic B
- if both email and LinkedIn are missing/invalid, raise a clear exception instead of inventing an ID

5d) Evidence ID
Formula:
- `evidence:<sha256(source_type|canonical_url|captured_at_iso|sha256(snippet_text_or_empty))>`

Notes:
- snippet_text_or_empty means empty string when snippet is None
- the inner snippet hash must also use sha256 hex UTF-8

5e) Draft ID
Formula:
- `draft:<contact_id>:seq<sequence_no>:v<variant_no>`

Rules:
- sequence_no and variant_no must come from deterministic inputs
- do not use DB auto-increment or timestamps

5f) Decision key and decision ID
Formula:
- `decision_key = sha256(work_item_id|contact_id|action_type|policy_pack_id|draft_id)`
- `decision_id = decision:<draft_id>:<decision_key>`

5g) Send ID and idempotency key
Formula:
- `send_id = send:<draft_id>:<channel>`
- `send_idempotency_key = send:<draft_id>:<channel>:v1`

Implementation quality requirements
- Use pure functions
- Add type hints
- Keep functions side-effect free
- Prefer standard library only unless the repo already has an established utility dependency for URL parsing / IDNA handling
- Add concise docstrings for non-obvious behavior
- Make invalid-input behavior deterministic and explicit

Testing requirements
Create focused unit tests for:
1. domain normalization
   - trims whitespace
   - lowercases
   - removes one leading www
   - removes port
   - strips trailing dot
   - parses full URL to host
   - handles IDNA conversion
   - returns None for invalid/empty input

2. email normalization
   - preserves plus tags
   - preserves dots
   - lowercases local part
   - normalizes domain
   - returns None for invalid input

3. linkedin normalization
   - removes query and fragment
   - removes trailing slash
   - keeps identity path
   - handles invalid input

4. seller/account/contact/evidence/draft/decision/send IDs
   - exact string outputs for representative fixtures
   - account fallback precedence:
     registry beats domain
     domain beats tmp hash
   - contact fallback precedence:
     email beats LinkedIn hash
     LinkedIn hash used only when normalized email absent
     missing both raises
   - evidence ID is stable across reruns with same input
   - decision key and send idempotency key are deterministic

5. replay-safety-oriented determinism
   - repeated calls with same inputs produce byte-for-byte identical outputs

Expected file-level result
- one Python module for normalization and ID generation
- one corresponding test module

Structure rules — must follow Epic A scaffold
- Do NOT create new root-level directories or root-level Python packages such as `shared/`, `common/`, `lib/`, or `core/`
- Keep all code inside the existing Epic A repo structure
- Reuse the existing Python package layout under `api/` and `worker/`
- Preferred placement order:
  1. an existing canonical utility module under `api/aose_api/` if one already exists
  2. otherwise a new small utility module under `api/aose_api/`
- Put tests under the existing API test layout, typically `api/tests/`
- Only modify `worker/` if required to keep imports, tests, or linting consistent with the current scaffold
- Avoid speculative restructuring, cross-package refactors, or introducing a new shared library in this ticket

Non-goals
- no DB uniqueness constraints yet
- no alias persistence yet
- no merge engine
- no policy engine implementation
- no structured events

Completion standard
Your final response after coding must include:
1. files changed
2. exact helpers added
3. any implementation assumptions kept strictly within contract
4. test cases added
5. commands run and results
6. any blocker that prevented exact compliance

Important
If the existing codebase already contains partial ID helpers, refactor them to match the locked contract rather than creating parallel variants.
If any required contract value is missing, check whether it is already locked in the Epic B contract before creating a placeholder. For B1, do not create new placeholders unless absolutely unavoidable.

Verification rules — must align to Epic A tooling
Run only the repo-standard verification commands relevant to files you changed. Prefer:
- `docker compose run --rm api pytest -q`
- `docker compose run --rm api ruff check .`
- `docker compose run --rm api ruff format --check .`

If the implementation touches worker files, also run:
- `docker compose run --rm worker pytest -q`
- `docker compose run --rm worker ruff check .`
- `docker compose run --rm worker ruff format --check .`

Do not rely on ad hoc local-only commands when the Epic A contract already defines containerized verification.

Dependency rules
- Prefer Python standard library only
- Do not add new third-party dependencies unless absolutely required for exact contract compliance
- If a new dependency is unavoidable, update the correct requirements file(s) under `api/` or `worker/`, explain why, and keep the addition minimal

If there is no obvious location, place the code where shared canonical utilities belong