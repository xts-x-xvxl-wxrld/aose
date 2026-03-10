# docs/epics/epic-h/spec-h4.md
# Spec H4 — Review UI

spec_id: spec-h4
epic: epic-h
title: "Review UI"
status: draft
version: "0.1"
date: "2026-03-08"

summary:
  goal: "Provide a one-screen review UI where a reviewer can inspect a draft, open anchor-linked evidence cards inline, inspect gate outcomes, and record a decision without leaving the page."
  outcome: "Approval no longer depends on hunting across provider tools, raw payloads, or separate screens."

scope:
  in_scope:
    - "Review screen loaded by draft_id."
    - "Draft preview panel."
    - "Evidence digest panel."
    - "Anchor list panel."
    - "Evidence cards panel."
    - "Gate outcomes panel."
    - "Decision controls panel."
    - "Inline evidence card highlighting/filtering from anchor clicks."
    - "Decision submission flow into H3 approval workflow."
  out_of_scope:
    - "No inbox."
    - "No sending console."
    - "No provider dashboards."
    - "No reply threading."
    - "No hidden dependency on raw provider payloads."
    - "No hiding STOP-class gate failures."

contract_touchpoints:
  loads_by:
    - "draft_id only"
  reads:
    - "OutreachDraft"
    - "PersonalizationAnchor"
    - "Evidence digest DTO from H1"
    - "canonical Evidence-derived evidence cards"
    - "gate outcomes relevant to approval"
  writes:
    - "ApprovalDecision via H3 action"
  depends_on:
    - "H1 digest builder"
    - "H2 draft + anchors"
    - "H3 approval persistence/routing"

required_panels:
  - draft_preview
  - evidence_digest
  - anchor_list
  - evidence_cards
  - gate_outcomes
  - decision_controls

evidence_card_required_fields:
  - evidence_id
  - claim_frame
  - snippet
  - url
  - source_type
  - captured_at

interaction_rules:
  - "Clicking an anchor filters or highlights linked evidence cards."
  - "Reviewer can approve, reject, or request rewrite without leaving the screen."
  - "Unanchored or unsupported claims are surfaced as review issues."
  - "Policy-blocking gates cannot be hidden by the UI."
  - "Review UI loads by draft_id only."
  - "Evidence cards are derived from canonical Evidence, not generated prose."

gate_visibility_requirements:
  - "DraftClaimEvidenceGate outcome visible before approval."
  - "EvidenceGate outcome visible before approval."
  - "ContactabilityGate outcome visible before approval."
  - "Any STOP-class gate visible and marked non-overridable."
  - "send_enabled=false may be shown as downstream send-disabled state, but it does not disable review decision controls."

behavior:
  page_load:
    - "Resolve draft by draft_id."
    - "Load draft subject/body."
    - "Load anchors for the draft."
    - "Build/load evidence digest."
    - "Render evidence cards from canonical Evidence rows."
    - "Load visible gate outcomes."
  anchor_interaction:
    - "Select anchor span in preview or anchor list."
    - "Highlight/filter linked evidence cards by evidence_ids."
    - "Allow user to inspect claim_frame, snippet, url, source_type, captured_at inline."
  review_issue_display:
    - "Show unanchored claims or REVIEW outcomes in a dedicated issue area."
    - "Show STOP-class gates as blocking banners/badges with no override affordance."
  decision_submission:
    - "Present statuses: approved, rejected, needs_rewrite, needs_more_evidence."
    - "Collect reviewer notes optionally."
    - "Submit to H3 approval action and reflect persisted result."

ui_invariants:
  - "Reviewer does not need to leave the review screen to inspect evidence context."
  - "No raw provider payload or hidden source dependency is required."
  - "No STOP-class gate may be hidden, collapsed away by default, or made overrideable."
  - "Evidence shown is canonical and traceable."

deliverables:
  - "Review page/screen keyed by draft_id"
  - "API/read models for draft, anchors, digest, evidence cards, gate outcomes"
  - "Anchor-to-evidence interaction behavior"
  - "Decision submission controls wired to H3"
  - "UI tests for evidence linking and decision flows"

acceptance_checks:
  - "Reviewer can inspect anchor-linked evidence cards inline."
  - "Reviewer can record approved/rejected/needs_rewrite/needs_more_evidence without leaving the screen."
  - "Approval does not require hunting for external context."
  - "Unanchored or unsupported claims are visibly surfaced."
  - "STOP-class gate failures remain visible and non-overridable."

ai_build_prompt: |
  Implement Spec H4 for Epic H review UI.
  
  Build a review screen that loads by draft_id only and renders all context needed for approval on one page.
  
  Required panels:
  - draft_preview
  - evidence_digest
  - anchor_list
  - evidence_cards
  - gate_outcomes
  - decision_controls
  
  Requirements:
  - Load OutreachDraft subject/body and PersonalizationAnchor rows.
  - Load or compute the H1 evidence digest.
  - Render evidence cards from canonical Evidence only, with fields:
    evidence_id, claim_frame, snippet, url, source_type, captured_at
  - Clicking an anchor in the draft preview or anchor list must filter/highlight the matching evidence cards.
  - Surface unanchored claims or unsupported claims as review issues.
  - Show gate outcomes before decision:
    DraftClaimEvidenceGate, EvidenceGate, ContactabilityGate, and any STOP-class gates.
  - STOP-class gates must be clearly visible and non-overridable in the UI.
  - Allow reviewer to record one of:
    approved, rejected, needs_rewrite, needs_more_evidence
    without leaving the review screen.
  - Submit decision into the H3 approval workflow, not into an ad hoc UI-only state.
  - Do not depend on raw provider payloads or external dashboards.
  - Do not add inbox, sending console, or reply-threading features.
  - Add UI tests proving anchor click -> evidence card highlight, visible gate outcomes, and in-screen decision recording.