# docs/epics/epic-h/spec-h1.md
# Spec H1 — Evidence digest builder

spec_id: spec-h1
epic: epic-h
title: "Evidence digest builder"
status: draft
version: "0.1"
date: "2026-03-08"

summary:
  goal: "Build a compact, renderable evidence digest for drafting and review from canonical SellerProfile, Account, Contact, and Evidence records only."
  outcome: "A derived DTO/view-model is produced for a given seller_id + account_id + contact_id + evidence_ids input and is usable by both copy generation and the review UI."

scope:
  in_scope:
    - "Load canonical SellerProfile, Account, Contact, and Evidence rows."
    - "Assemble a compact evidence digest object with the locked required shape."
    - "Apply deterministic evidence ordering rules."
    - "Return a renderable digest for copy generation and review UI."
    - "Optionally read Scorecard as non-authoritative context if present."
    - "Emit structured events for digest build success/failure."
  out_of_scope:
    - "No new canonical EvidenceDigest table."
    - "No mutation of canonical Evidence rows."
    - "No new claims, scores, or inferred persona facts."
    - "No provider payload dependency."
    - "No sending behavior."
    - "No approval decision recording."

contract_touchpoints:
  consumes:
    - "WorkItem stage=copy_generate payload_version=1"
    - "payload fields: seller_id, account_id, contact_id, evidence_ids"
  reads:
    - "SellerProfile"
    - "Account"
    - "Contact"
    - "Evidence"
    - "Scorecard (optional, read-only)"
  produces:
    - "Derived evidence digest DTO only"
    - "structured event: evidence_digest_built"
    - "structured event: work_item_failed_contract"
    - "structured event: work_item_failed_transient"
    - "structured event: work_item_parked"

inputs:
  required:
    - seller_id
    - account_id
    - contact_id
    - evidence_ids
  optional:
    - language
    - channel
  defaults:
    language: en
    channel: email

output_shape:
  seller_summary:
    required_fields:
      - seller_id
      - offer
      - constraints
  account_summary:
    required_fields:
      - account_id
      - name
      - domain
      - country
  contact_summary:
    required_fields:
      - contact_id
      - full_name
      - role
      - channels
  evidence_items:
    item_required_fields:
      - evidence_id
      - source_type
      - url
      - captured_at
      - claim_frame
      - snippet
  drafting_constraints:
    required_fields:
      - policy_pack_id
      - avoid_claims
      - allowed_channels
      - language

deterministic_rules:
  evidence_ordering:
    - "Sort by source trust descending."
    - "If equal trust, sort by captured_at descending."
    - "If still tied, sort by evidence_id lexicographically."
  source_trust_order:
    - "registry/api"
    - "first-party site"
    - "official profiles"
    - "reputable directories"
    - "general web extracts"
  digest_persistence:
    mode: "derived_object_only"
    rule: "Digest may be recomputed on demand and optionally cached as a non-authoritative optimization only."

behavior:
  happy_path:
    - "Validate required payload fields exist."
    - "Load seller/account/contact rows by canonical ID."
    - "Load each evidence row by evidence_id."
    - "Fail contract if any required canonical record is missing."
    - "Build seller/account/contact summaries from canonical fields only."
    - "Build evidence_items from canonical Evidence only."
    - "Build drafting_constraints from SellerProfile.constraints plus policy_pack_id."
    - "Return renderable digest object."
  optional_context:
    - "If Scorecard exists, it may be read for UI context only."
    - "Scorecard content must not become new evidence."
  invariants:
    - "Digest contains only facts already present in canonical records."
    - "Digest does not invent claims, scores, or persona facts."
    - "Digest does not include secrets or provider credentials."
    - "Digest is renderable by the Epic H review UI."
    - "Digest does not mutate canonical state."

error_handling:
  contract_error:
    examples:
      - "missing seller/account/contact canonical record"
      - "missing required payload field"
      - "unsupported payload_version"
      - "referenced evidence_id not found"
    action: "park immediately as parked:contract_error"
  transient_error:
    examples:
      - "db timeout"
      - "temporary read failure"
    action: "retry while budget remains"
  budget_exhausted:
    action: "park as parked:budget_exhausted"

deliverables:
  - "Digest builder service/module"
  - "DTO/schema definition for evidence digest"
  - "Unit tests for ordering, shape, and contract failures"
  - "Integration path from copy_generate handler to digest builder"
  - "Structured event emission for success/failure"

acceptance_checks:
  - "Given seller_id + account_id + contact_id + evidence_ids, the system returns a compact evidence digest with the required shape."
  - "Digest content is derived solely from canonical rows."
  - "Evidence ordering follows source trust, then captured_at desc, then evidence_id."
  - "Missing canonical records cause deterministic parked:contract_error."
  - "No new canonical table is introduced."

ai_build_prompt: |
  Implement Spec H1 for Epic H using the existing Epic B models and Epic C worker/event conventions.
  
  Build an Evidence Digest builder that consumes copy_generate payload v1:
  { seller_id, account_id, contact_id, evidence_ids, channel?, language?, sequence_no?, variant_no? }.
  
  Requirements:
  - Read only canonical SellerProfile, Account, Contact, Evidence, and optional Scorecard.
  - Do NOT create any new canonical EvidenceDigest table.
  - Produce a derived DTO/view-model only.
  - Required digest shape:
    seller_summary { seller_id, offer, constraints }
    account_summary { account_id, name, domain, country }
    contact_summary { contact_id, full_name, role, channels }
    evidence_items[] { evidence_id, source_type, url, captured_at, claim_frame, snippet }
    drafting_constraints { policy_pack_id, avoid_claims, allowed_channels, language }
  - Evidence ordering must be deterministic:
    1) source trust desc using locked trust order
    2) captured_at desc
    3) evidence_id lexicographically
  - Digest must contain only facts already present in canonical records.
  - No new claims, no inferred persona facts, no mutation of canonical Evidence.
  - Emit structured events:
    evidence_digest_built, work_item_failed_contract, work_item_failed_transient, work_item_parked.
  - Missing required canonical rows or evidence_ids must park as contract_error.
  - Add unit tests for required shape, ordering, and contract failure behavior.