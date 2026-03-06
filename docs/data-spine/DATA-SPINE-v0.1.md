# DATA-SPINE-V0.1.md

Status: draft (v0.1)
Purpose: define the shared data contract (“spine”) that keeps the system restart-safe, parallel-safe, and modular.

---

## 0) Design intent

The system is an ecosystem of independent modules (“organs”) coordinated through one shared language (canonical schemas) and one shared set of constraints (caps, stop rules, idempotency). Modules can be swapped without rewriting the whole pipeline because they only interact through stable handoff objects and canonical record shapes.

v0.1 targets a minimal foundation that supports an end-to-end slice with sending gated behind approval, while keeping policy-heavy choices configurable and future-tightenable.

---

## 1) Spine invariants (non-negotiable)

1. Queue-driven handoff only: modules do not call each other directly; they write canonical records and enqueue the next WorkItem.
2. Replay safety: reprocessing a WorkItem must be a no-op or deterministic overwrite; never duplicate side effects.
3. Deterministic identity: canonical IDs + alias sets + deterministic merge precedence.
4. Evidence grounding: scoring + copy must reference Evidence IDs.
5. PolicyPack controls behavior-critical values (caps, thresholds, send enablement).

---

## 2) Universal envelope: WorkItem

A WorkItem is the only object that flows through the queue. It stays small and stable.

### 2.1 Canonical shape

```json
{
  "work_item_id": "wi_01J3X9KJ0G2E0N9M6K8T1Z2Y7R",
  "entity_ref": { "type": "account", "id": "account:SI-1234567" },
  "stage": "account_discovery",
  "payload": { "v": 1, "data": { "query_object_id": "q_87f1" } },
  "attempt_budget": { "remaining": 3, "policy": "standard" },
  "idempotency_key": "acctdisc:account:SI-1234567:q_87f1:v1",
  "trace": {
    "run_id": "run_2026-02-25T10:12:33Z_4b7c",
    "parent_work_item_id": "wi_01J3X9J8K7...",
    "correlation_id": "corr_account:SI-1234567",
    "policy_pack_id": "safe_v0_1"
  },
  "created_at": "2026-02-25T10:12:33Z"
}
```

### 2.2 Field semantics

* `entity_ref`: anchor for dedup + storage joins; avoids copying full records into the queue.
* `stage`: routing + responsibility boundary. Missing preconditions at a stage are a contract failure.
* `payload`: stage-specific data, versioned by `payload.v`. Workers may support multiple versions per stage.
* `attempt_budget`: caps retries and exploration; decremented on meaningful attempts (source calls, model calls, paid enrichments).
* `idempotency_key`: uniqueness handle for side effects under at-least-once processing.
* `trace`: auditability across stages; must include `policy_pack_id`.

### 2.3 Idempotency rules (v0.1)

Idempotency is guaranteed by two layers:

* Storage uniqueness on side-effect tables using `idempotency_key`.
* Deterministic dedup/merge rules using canonical IDs + aliases.

Reprocessing a WorkItem must be either:

* a no-op (output already exists for `idempotency_key`), or
* a deterministic overwrite that preserves invariants (no duplicate records, no extra sends).

---

## 3) Canonical identifiers, aliases, and deterministic dedup

### 3.1 ID namespaces (strings)

```text
seller:<slug>

account:<country>-<registry_id>              (preferred)
account:<normalized_domain>                  (fallback)
account:tmp:<hash>                           (last resort)

contact:<account_id>:<normalized_email>      (preferred)
contact:<account_id>:<hash(linkedin_url)>    (fallback)

evidence:<hash(source_type+url+captured_at+snippet_hash)>
econtent:<hash(content_hash)>

score:<entity_ref>:<date_or_hash>

draft:<contact_id>:<sequence_id>:<variant>
decision:<draft_id>:<timestamp_or_hash>
send:<draft_id>:<channel>
```

### 3.2 Alias-based identity model (v0.1)

Accounts and contacts maintain an alias set so identity can “upgrade” without rewriting history.

* Account aliases:

  * `registry` (source + id)
  * `domains`
  * `legal_names` (normalized)

Upgrade path: if a domain-based account later gains a registry identifier, canonical ID becomes registry-based through deterministic merge, domain preserved as alias.

### 3.3 Deterministic dedup keys

Accounts:

1. `country + registry_id` (primary)
2. `normalized_domain` (secondary)
3. `name + address` (deferred; only if address normalization is reliable)

Contacts:

1. `normalized_email` (primary)
2. `linkedin_url` (secondary)
3. `name + account_id + role_cluster` (deferred; high collision risk)

### 3.4 Deterministic merge precedence

Conflict resolution order (v0.1):

1. higher-trust source wins
2. if equal trust, newer capture wins
3. if still tied, stable tie-breaker (lexicographic on source id)

---

## 4) Canonical record shapes (v0.1)

WorkItems reference canonical records; they do not carry the full world.

### 4.1 SellerProfile

```json
{
  "seller_id": "seller:soultan",
  "policy_pack_id": "safe_v0_1",
  "offer": {
    "what": "dispensing consumables for adhesive dispensing",
    "where": ["SI", "AT", "DE", "IT"],
    "who": ["EMS", "electronics manufacturing", "automotive suppliers"],
    "positioning": ["traceable QA docs", "ISO-certified sourcing", "reliable supply"]
  },
  "constraints": {
    "avoid_claims": ["TBD policy list"],
    "allowed_channels": ["email", "linkedin"],
    "languages": ["en"]
  },
  "created_at": "2026-02-25T09:40:00Z",
  "v": 1
}
```

### 4.2 QueryObject (structured search intent, not prose)

```json
{
  "query_object_id": "q_87f1",
  "seller_id": "seller:soultan",
  "buyer_context": "EMS providers in Slovenia producing electronics assemblies",
  "priority": 0.8,
  "keywords": ["electronics manufacturing services", "SMT", "EMS", "production"],
  "exclusions": ["jobs", "consumer", "training"],
  "rationale": "Targets production orgs likely using dispensing consumables",
  "v": 1
}
```

### 4.3 AccountCandidate / Account

```json
{
  "account_id": "account:SI-1234567",
  "aliases": {
    "registry": [{ "source": "AJPES", "id": "1234567" }],
    "domains": ["example.si"],
    "legal_names": ["example doo"]
  },
  "name": "Example d.o.o.",
  "domain": "example.si",
  "country": "SI",
  "provenance": [
    { "adapter": "registry_search", "query_object_id": "q_87f1", "captured_at": "2026-02-25T10:13:00Z" }
  ],
  "evidence_ids": ["evidence:9b2f..."],
  "confidence": 0.72,
  "status": "candidate",
  "v": 1
}
```

Promotion rule (v0.1): candidate → `status: "target"` when scorecard thresholds are met and dedup passes.

### 4.4 Evidence (pointer-first) and optional EvidenceContent

Evidence is first-class because scoring and copy must be grounded.

```json
{
  "evidence_id": "evidence:9b2f1c...",
  "source_type": "web",
  "url": "https://example.si/services/smt",
  "captured_at": "2026-02-25T10:14:12Z",
  "snippet": "Surface-mount assembly and conformal coating services...",
  "claim_frame": "Company offers EMS/SMT production services",
  "provenance": { "adapter": "web_search", "query_object_id": "q_87f1" },
  "content_ref": { "kind": "extract", "id": "econtent:4fa1..." },
  "v": 1
}
```

```json
{
  "evidence_content_id": "econtent:4fa1...",
  "content_hash": "sha256:....",
  "kind": "extract",
  "text": "Cleaned text extracted from the page...",
  "raw_ref": { "kind": "none", "id": null },
  "captured_at": "2026-02-25T10:14:12Z",
  "v": 1
}
```

Capture policy (v0.1): store URL+snippet+claim_frame always; store extracts by default for high-trust sources; pointer-only for noisy sources unless promotion/draft anchoring requires more. Retention windows are policy-configurable.

### 4.5 Scorecard (fit + intent separated)

```json
{
  "scorecard_id": "score:account:SI-1234567:2026-02-25",
  "policy_pack_id": "safe_v0_1",
  "entity_ref": { "type": "account", "id": "account:SI-1234567" },
  "fit": {
    "score": 0.78,
    "confidence": 0.70,
    "reasons": [{ "text": "Matches EMS segment", "evidence_ids": ["evidence:9b2f1c..."] }]
  },
  "intent": {
    "score": 0.32,
    "confidence": 0.55,
    "reasons": [{ "text": "No near-term trigger found", "evidence_ids": [] }]
  },
  "computed_at": "2026-02-25T10:20:00Z",
  "v": 1
}
```

### 4.6 ContactCandidate / Contact (with validation levels)

```json
{
  "contact_id": "contact:account:SI-1234567:john.doe@example.si",
  "account_id": "account:SI-1234567",
  "full_name": "John Doe",
  "role": { "cluster": "economic_buyer", "title": "Head of Production", "confidence": 0.66 },
  "channels": [
    {
      "type": "email",
      "value": "john.doe@example.si",
      "validated": "domain_ok",
      "confidence": 0.82,
      "validated_at": "2026-02-25T10:29:10Z",
      "source_trace": ["adapter:people_search_a"]
    }
  ],
  "provenance": [{ "adapter": "people_search_a", "captured_at": "2026-02-25T10:28:00Z" }],
  "status": "candidate",
  "v": 1
}
```

Validation levels (v0.1 minimum for automated flow):

* Email: `unverified` → `syntax_ok` → `domain_ok` → `provider_verified` → `human_verified` (min: `domain_ok`)
* LinkedIn: `unverified` → `profile_exists` → `human_verified`

### 4.7 OutreachDraft with personalization anchors

Anchors link text spans to Evidence IDs.

```json
{
  "draft_id": "draft:contact:account:SI-1234567:john.doe@example.si:seq1:v1",
  "policy_pack_id": "safe_v0_1",
  "contact_id": "contact:account:SI-1234567:john.doe@example.si",
  "account_id": "account:SI-1234567",
  "channel": "email",
  "language": "en",
  "subject": "Quick question about dispensing consumables",
  "body": "Hi John, ...",
  "anchors": [
    { "span": "noticed you run SMT assembly", "evidence_ids": ["evidence:9b2f1c..."] }
  ],
  "risk_flags": [],
  "created_at": "2026-02-25T10:40:00Z",
  "v": 1
}
```

### 4.8 ApprovalDecision (explicit state transition)

```json
{
  "decision_id": "decision:draft:...:2026-02-25T11:00:00Z",
  "decision_key": "hash(work_item_id+contact_id+action_type+policy_pack_id+draft_id)",
  "policy_pack_id": "safe_v0_1",
  "draft_id": "draft:...",
  "status": "approved",
  "reviewer_id": "human:TBD",
  "reviewer_role": "operator",
  "overridden_gates": [],
  "notes": "OK to send",
  "decided_at": "2026-02-25T11:00:00Z",
  "v": 1
}
```

Decision statuses (v0.1): `approved | rejected | needs_rewrite | needs_more_evidence`.

### 4.9 SendAttempt (highest-risk side effect)

```json
{
  "send_id": "send:draft:...:email",
  "policy_pack_id": "safe_v0_1",
  "draft_id": "draft:...",
  "channel": "email",
  "provider": "SEND_SRC_01",
  "status": "queued",
  "provider_message_id": null,
  "idempotency_key": "send:draft:...:email:v1",
  "created_at": "2026-02-25T11:02:00Z",
  "v": 1
}
```

Provider interface (v0.1 minimal): `enqueue(send_attempt) -> provider_message_id`, `poll(provider_message_id) -> status`.

### 4.10 StructuredEvent (machine-readable audit trail, redacted by default)

```json
{
  "event_id": "ev_01J3XAB2...",
  "occurred_at": "2026-02-25T10:14:30Z",
  "module": "account_discovery",
  "work_item_id": "wi_01J3X9KJ...",
  "entity_ref": { "type": "account", "id": "account:SI-1234567" },
  "stage": "account_discovery",
  "kind": "adapter_call",
  "status": "ok",
  "metrics": { "candidates_found": 12, "new_unique": 7, "latency_ms": 842 },
  "refs": { "query_object_id": "q_87f1", "adapter": "registry_search", "evidence_ids": ["evidence:9b2f..."] },
  "policy_pack_id": "safe_v0_1",
  "v": 1
}
```

PII policy (v0.1): events must not emit raw emails/phones or full message bodies; reference IDs/hashes only.

---

## 5) Stage vocabulary and payload contracts (v0.1)

### 5.1 Stage set

```text
seller_profile_build
query_objects_generate
account_discovery
intent_fit_scoring
people_search
contact_enrichment
copy_generate
approval_request
sending_dispatch

parked:<reason_code>
```

### 5.2 Stage-to-payload mapping

* `seller_profile_build`: seller raw inputs or seller_id reference
* `query_objects_generate`: seller_id
* `account_discovery`: query_object_id (+ optional adapter plan)
* `intent_fit_scoring`: account_id (+ evidence digest refs)
* `people_search`: account_id (+ role targets)
* `contact_enrichment`: contact_id (+ validations requested)
* `copy_generate`: seller_id + account_id + contact_id + evidence_ids
* `approval_request`: draft_id
* `sending_dispatch`: draft_id + decision_id

Each payload stays versioned per stage (`payload.v`).

---

## 6) Global constraints and budgets (policy-driven)

v0.1 requires explicit caps so discovery cannot balloon; numbers live in PolicyPack and are referenced by `policy_pack_id`.

PolicyPack `safe_v0_1` (authoritative defaults) includes: `send_enabled=false`, run caps, per-account/per-contact caps, thresholds, rate limits (only when send enabled), timeouts/retries, and circuit breakers.

Attempt budgets:

* Decrement on meaningful attempts: `source_call`, `model_call`, `paid_enrichment_call`.
* When budget reaches zero: park deterministically with `budget_exhausted`.

---

## 7) Trust ranking and evidence categories

### 7.1 Source trust ranking (default)

Registry/API > first-party site > official profiles > reputable directories > general web extracts.

### 7.2 Evidence categories (v0.1)

* Firmographic (industry/size/location)
* Persona fit (title/department/seniority)
* Trigger (hiring/funding/expansion/new site/compliance cycle)
* Technographic (tools/stack)

---

## 8) Error taxonomy and deterministic routing (v0.1)

Error codes: `contract_error | transient_error | budget_exhausted | no_signal | policy_blocked | needs_human`.

Routing rules (deterministic):

* `contract_error` → park immediately (no retries)
* `transient_error` → retry while budget remains (with backoff per policy)
* `budget_exhausted` / `no_signal` → park with reason
* `policy_blocked` → park with flags (STOP gates are not overridable)
* `needs_human` → park into review lane

---

## 9) Governance gates (safe defaults wired into the spine)

Decision model: each gate returns `PASS | REVIEW | STOP`.

Hard STOP examples (safe_v0_1):

* missing website/domain AND missing unique company identifier
* free email domains for send
* suppression hit
* generic mailbox only for send
* any cap exceeded
* send_enabled=false → no SendAttempt created

Draft claim evidence gate:

* REVIEW if any specific claim lacks linked Evidence IDs; required rewrite behavior is to strip unsupported claims or add evidence.

---

## 10) Storage-level requirements (contract, not implementation)

Minimum constraints to enforce invariants:

* Unique indexes on:

  * `work_items.idempotency_key`
  * `send_attempts.idempotency_key`
  * canonical IDs (`account_id`, `contact_id`, `evidence_id`, `draft_id`)
* Queryable indexes on:

  * `work_items.stage`, `work_items.entity_ref.id`, `work_items.trace.correlation_id`
  * `events.work_item_id`, `events.entity_ref.id`, `events.occurred_at`

---

## 11) Security and PII baseline (v0.1)

* Canonical tables may store PII (contacts, drafts) for operation.
* Structured events/logs must be redacted by default (IDs/hashes only).
* Secrets never live in the spine; they live in a separate secrets layer.
* Retention is policy-defined; defaults include shorter retention for logs/events and longer for canonical audit objects (drafts/send attempts).

---

## 12) Module manifest (contract-to-organ link)

Each organ declares what it consumes/produces and how it spends budget.

```json
{
  "module_name": "intent_fit_scoring",
  "module_version": "0.1.0",
  "consumes": [{ "stage": "intent_fit_scoring", "payload_versions": [1] }],
  "produces": [
    { "stage": "people_search", "payload_version": 1 },
    { "stage": "parked:no_signal", "payload_version": 1 }
  ],
  "side_effects": ["write_scorecard"],
  "idempotency": { "strategy": "by_work_item_key" },
  "budget_spend": { "per_item_max_calls": 5, "decrement_on": ["model_call", "source_call"] },
  "v": 1
}
```

---

## 13) v0.1 scope boundary (explicitly out)

* Deep email verification beyond `domain_ok` (provider_verified is deferred)
* Raw HTML/PDF snapshot storage as a default (optional later, policy-toggled)
* Address normalization + name/address merge logic for domain-less accounts (deferred)
* Full send provider integration beyond sandbox/minimal interface (deferred; sending remains gated)

---

## 14) Implementation alignment

Epic B (“Data Spine v0.1 as database truth”) builds tables and helpers matching these contracts: WorkItem, SellerProfile, QueryObject, Account(+aliases), Evidence(+content), Scorecard, Contact(+aliases), Draft(+anchors), ApprovalDecision, SendAttempt, plus uniqueness constraints proving replay safety.
