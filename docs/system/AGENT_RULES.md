# AGENT_RULES.md

Purpose: enforce deterministic, rerunnable delivery of epics (starting with Epic A) using doc-driven contracts. Prompts trigger execution; specifications live in-repo.

This file is authoritative for how the build agent plans, edits, verifies, and reports.

---

## 0) Non-negotiables

1) No silent decisions.
- If a decision affects repo structure, frameworks, ports, env vars, service names, Make targets, CI gates, or dependencies: it must be sourced from the Epic CONTRACT file.
- If the CONTRACT is missing the decision: register a placeholder and proceed using the placeholder’s default stub.

2) Plan before edit.
- Write a concrete action plan (task graph) before creating/modifying any file.

3) Idempotent by default.
- Rerunning the same epic must not create duplicates or drift (no “generated twice” configs, no divergent scaffolding).

4) Verify against acceptance checks.
- Epic acceptance is not “looks right.” Run the specified commands and record pass/fail.

5) Scope control.
- Only touch files required by the epic plan. No opportunistic refactors.

6) Safety defaults.
- PolicyPack safe_v0_1 is the default posture; sending remains disabled unless explicitly enabled by a later epic contract.

---

## 1) Repository documents and authority order

When executing an epic, read these in order and treat earlier items as higher priority:

1) `docs/system/AGENT_RULES.md` (this file)
2) `docs/epics/<epic-id>/SPEC.md` (human intent, acceptance, boundaries)
3) `docs/epics/<epic-id>/CONTRACT.yaml` (machine contract; single source of truth for build decisions)
4) `docs/epics/<epic-id>/PLACEHOLDERS.md` (allowed TBDs + required default stub behavior)
5) `docs/policy/policy-pack-safe-v0_1.md` (guardrails defaults)
6) `docs/data-spine/DATA-SPINE-v0.1.md` (canonical shapes and invariants)

If any conflict exists:
- CONTRACT.yaml overrides everything except AGENT_RULES.md.
- SPEC.md defines intent; CONTRACT.yaml defines implementation.

---

## 2) Prompt handling contract (what prompts may contain)

Prompts are triggers, not specs. The prompt may include:
- Epic identifier (example: “Epic A”)
- Execution mode: “plan → scaffold → verify”
- Instruction: “treat CONTRACT.yaml as authoritative; do not invent decisions”
- Output requirement: “use the standard output template”

Prompts must not embed:
- architecture choices, ports, folder trees, framework selection
- dependency selection
- CI details
- Make target behaviors

If the prompt contains implementation details that contradict CONTRACT.yaml, ignore the prompt details and follow CONTRACT.yaml. Record the mismatch in the report under “Conflicts”.

---

## 3) Standard output template (mandatory)

The agent output MUST follow this template, in this order:

1) Read Summary
- Files read (full paths)
- Epic id + contract version identifier (hash or last modified timestamp)
- Environment assumptions (OS, shell, runtime availability)

2) Constraints Digest
- A checklist derived from CONTRACT.yaml (ports, services, folders, env vars, Make targets, CI jobs)

3) Action Plan (no edits yet)
For each task:
- Task id (A1/A2/A3…)
- Purpose
- Files to create/modify (explicit list)
- Commands to run (explicit list)
- Acceptance mapping (which SPEC acceptance line it satisfies)
- Idempotency note (how rerun stays stable)

4) Execution Log
- Created paths
- Modified paths
- High-level summary of changes per file (no handwaving)

5) Verification Log
- Commands executed
- Pass/fail
- If unexecuted: mark “UNEXECUTED” and state why (missing tool, permissions, etc.)
- Include the expected success signal (port open, test suite green, etc.)

6) Placeholders
- Only placeholders registered in PLACEHOLDERS.md
- For each: placeholder id, reason, stub behavior, follow-up ticket pointer (if present)

7) Conflicts (if any)
- Prompt vs contract mismatches
- Existing repo state vs contract mismatches
- Resolutions taken (must favor contract)

No additional sections.

---

## 4) Placeholder protocol (controlled uncertainty)

A placeholder is permitted only if it is registered in:
`docs/epics/<epic-id>/PLACEHOLDERS.md`

Rules:
- If a required contract detail is missing, the agent must:
  1) add a placeholder entry,
  2) implement the default stub behavior defined by the placeholder,
  3) proceed without pausing for questions.

- “TODO” markers in code are not substitutes for placeholders.
- All placeholders must be enumerable and searchable by a stable id format:
  `PH-<epic-id>-<nnn>` (example: `PH-EPIC-A-001`)

Each placeholder entry must include:
- Placeholder id
- Missing decision
- Default stub behavior (what gets generated now)
- Impact on acceptance (must not block Epic A acceptance unless SPEC allows)
- Follow-up acceptance test for later epic

---

## 5) Determinism rules for file generation

General:
- Prefer minimal, stable scaffolding.
- Avoid generators that produce nondeterministic output (timestamps, random ids, non-locked dependency graphs).

Idempotency:
- If a file exists, patch it deterministically:
  - preserve unrelated content
  - only change the minimal required lines/blocks
- Never duplicate config blocks (compose services, CI steps, Make targets).
- Never create multiple competing configs for the same concern.

Naming and structure:
- Create exactly the folder tree specified by CONTRACT.yaml.
- Do not add extra top-level folders unless required by CONTRACT.yaml.

Dependencies:
- Use pinned or constrained versions where practical.
- Lock files (poetry.lock, uv.lock, package-lock.json) are allowed only if CONTRACT.yaml specifies them.

Secrets:
- Never commit `.env`.
- Always commit `.env.example` with safe dummy values.

---

## 6) Epic A execution procedure (plan → scaffold → verify)

This is the default procedure used unless an epic overrides it explicitly.

Phase 1: Plan
- Parse SPEC.md + CONTRACT.yaml into a task graph.
- Identify parallel lanes by file ownership:
  - Infra lane: compose/Make/CI/api/worker scaffolding
  - Web lane: web/ only
- Confirm acceptance checks are representable as commands.

Phase 2: Scaffold
- Create repo skeleton exactly as contracted.
- Create compose stack for Postgres + Redis (service names/ports per contract).
- Create minimal API and worker skeletons sufficient to run and connect.
- Create minimal web skeleton (only if CONTRACT.yaml requires; otherwise stub folder + README).

Phase 3: Verify
- Run the acceptance commands from SPEC.md (or CONTRACT.yaml if commands live there).
- Minimum Epic A gating:
  - `make dev` results in API up + DB reachable
  - API can connect to Postgres
  - worker can connect to Redis
  - CI sanity pipeline exists and would fail on lint/test failures (verified by local equivalents)

If verification cannot be executed in the current environment, output:
- the exact command
- the expected success signal
- the reason it was not executed

---

## 7) Minimal safety and governance alignment

Defaults:
- PolicyPack safe_v0_1 is assumed unless CONTRACT.yaml specifies otherwise.
- `send_enabled` must remain false during Epic A.
- Any future sending logic must be separated and gated behind approval states; Epic A must not implement sending.

Bounded behavior:
- Respect caps and guardrails as design constraints. Even if not implemented in Epic A, reserve the configuration touchpoints so later epics plug in without refactors.

Auditability:
- Prefer explicit, readable configs over clever abstractions.
- Ensure logs and outcomes are reproducible (no reliance on external SaaS state for Epic A).

---

## 8) Merge and collaboration rules (two-person team)

- File ownership is enforced to avoid nondeterministic merges:
  - Infra owner: root tooling, compose, CI, api/, worker/, docs/system, docs/epics
  - Web owner: web/
- If a change crosses ownership boundaries, split it into two commits:
  1) infra commit (root + api/worker + docs)
  2) web commit (web/ only)


End of file.