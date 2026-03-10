# docs/epics/epic-h/spec-h3.md
# Spec H3 — Approval workflow

spec_id: spec-h3
epic: epic-h
title: "Approval workflow"
status: draft
version: "0.1"
date: "2026-03-08"

summary:
  goal: "Store approval as an explicit ApprovalDecision record and route deterministically from approval_request to the correct next stage or parked outcome."
  outcome: "Review actions become replay-safe canonical decisions rather than informal notes."

scope:
  in_scope:
    - "Consume approval_request WorkItems."
    - "Record ApprovalDecision as canonical data."
    - "Validate reviewer authority against canonical roles."
    - "Enforce deterministic decision_key / decision_id behavior."
    - "Route by decision status."
    - "Show non-overridable STOP-class gate outcomes as blocking context."
  out_of_scope:
    - "No external sending."
    - "No provider dashboard logic."
    - "No policy pack management UI."
    - "No inbox/reply features."
    - "No unstructured text-note-only approval."
    - "No override of HardSafetyGate, BudgetGate, suppression, or complaint STOP outcomes."

contract_touchpoints:
  consumes:
    - "WorkItem stage=approval_request payload_version=1 payload={draft_id}"
  reads:
    - "OutreachDraft"
    - "Contact"
    - "gate outcomes / review context emitted upstream"
  writes:
    - "ApprovalDecision"
  produces:
    - "WorkItem stage=sending_dispatch payload_version=1 payload={draft_id, decision_id} when approved"
    - "WorkItem stage=parked:rejected payload_version=1 payload={draft_id, decision_id}"
    - "WorkItem stage=parked:needs_rewrite payload_version=1 payload={draft_id, decision_id}"
    - "WorkItem stage=parked:needs_more_evidence payload_version=1 payload={draft_id, decision_id}"

decision_model:
  required_fields:
    - decision_id
    - decision_key
    - draft_id
    - status
    - reviewer_id
    - reviewer_role
    - policy_pack_id
    - decided_at
  optional_fields:
    - notes
    - overridden_gates

decision_statuses:
  - approved
  - rejected
  - needs_rewrite
  - needs_more_evidence

deterministic_rules:
  decision_key_formula: "sha256(work_item_id|contact_id|action_type|policy_pack_id|draft_id)"
  decision_id_formula: "decision:<draft_id>:<decision_key>"
  approval_request_uniqueness_basis:
    - decision_key
  replay_behavior:
    - "Lookup by decision_key and reuse existing decision_id."
    - "Replay must not create duplicate decisions."

authority_rules:
  viewer:
    may_record_decision: false
    may_request_rewrite: false
    may_approve_send: false
  operator:
    may_record_decision: true
    allowed_statuses:
      - approved
      - rejected
      - needs_rewrite
      - needs_more_evidence
    may_override_review_outcomes:
      - FitScoreGate
      - EvidenceGate
      - RoleRelevance
    may_not_override_stop_outcomes:
      - HardSafetyGate
      - BudgetGate
      - suppression
      - complaint
  admin:
    inherits: operator

routing_rules:
  approved:
    next_stage: sending_dispatch
    payload_fields:
      - draft_id
      - decision_id
  rejected:
    next_stage: parked:rejected
    payload_fields:
      - draft_id
      - decision_id
  needs_rewrite:
    next_stage: parked:needs_rewrite
    payload_fields:
      - draft_id
      - decision_id
  needs_more_evidence:
    next_stage: parked:needs_more_evidence
    payload_fields:
      - draft_id
      - decision_id

gating_visibility_requirements:
  - "DraftClaimEvidenceGate outcome must be visible before final approval."
  - "EvidenceGate outcome must be visible before final approval."
  - "ContactabilityGate outcome must be visible before final approval."
  - "Any STOP-class gate must be visible and non-overridable in UI."
  - "send_enabled=false does not block recording approval, but blocks actual downstream sending behavior."

behavior:
  happy_path:
    - "Validate draft_id exists."
    - "Load draft and associated review context."
    - "Resolve contact_id from draft."
    - "Compute decision_key using work_item_id, contact_id, action_type, policy_pack_id, and draft_id."
    - "Check reviewer_role authority."
    - "Persist ApprovalDecision using deterministic decision_id."
    - "Commit ApprovalDecision before enqueueing downstream stage."
    - "Route deterministically by status."
    - "Emit approval_recorded and work_item_completed/work_item_parked."
  replay_path:
    - "If decision_key already exists, reuse existing decision_id."
    - "Do not insert duplicate ApprovalDecision."
  invalid_authority_path:
    - "Reject viewer decision attempts as contract/policy failure for this stage."
  override_path:
    - "Allow override only for REVIEW-class gates listed in authority rules."
    - "Do not allow override of STOP-class gates."

error_handling:
  contract_error:
    examples:
      - "missing draft_id"
      - "draft not found"
      - "unsupported payload_version"
      - "viewer attempted approval"
      - "invalid status"
    action: "park immediately"
  transient_error:
    action: "retry while budget remains"

deliverables:
  - "approval_request handler"
  - "ApprovalDecision persistence service"
  - "decision_key helper"
  - "authority validator"
  - "routing mapper from decision status -> next stage"
  - "unit and integration tests for replay and routing"

acceptance_checks:
  - "ApprovalDecision is stored as an explicit canonical record."
  - "Decision status deterministically drives next stage or parked outcome."
  - "Replay of the same approval action reuses decision_id via decision_key."
  - "Viewer cannot approve or reject."
  - "STOP-class gates remain visible and non-overridable."
