# Ticket Template

## 1. Files to read
- `docs/data-spine-v0.1.md`
- `CONTRACT.yaml` (if exists for Epic)
- `docs/policy/*`
- `PLACEHOLDERS.md`

## 2. Forbidden assumptions
- Do not assume network calls succeed natively without budget checks.
- Do not add API dependencies unless explicitly scoped.
- Do not use real user data in test fixtures.
- Do not configure default Send behaviors (must remain gated).

## 3. Output artifacts
- Tested Python logic with 100% boundary coverage.
- `.env` template additions (if any).
- `docs/manifests/<module>.yaml` describing stage transformations.

## 4. Placeholders raised
- (List `PH-*` IDs created during this ticket if required decisions were open or missing).
