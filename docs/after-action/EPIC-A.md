# Epic A After-Action Hardening Pack

## 1. Friction log
- 2026-03-04: “make” not available on Windows; PATH changes not persistent across shells.
- 2026-03-04/05: confusion around running healthz from host vs container; “docker compose exec Invoke-WebRequest …” misuse.
- 2026-03-04/05: Windows-specific RQ/scheduler import failure (“cannot find context for 'fork' …”) when running worker logic on Windows.
- 2026-03-04: lint failures for unused imports in tests (F401 etc.).
- 2026-03-05: broken/duplicate DATABASE_URL occurrences (postgresql+psycopg).

## 2. Root causes
- Dev environment lacked native Windows wrapper scripts causing reliance on external tools (Make).
- Unclear boundaries for executing tests and healthchecks (host vs container execution).
- Worker logic depends on `rq` and Unix fork context, fundamentally incompatible with Windows execution.
- CI pipeline caught unused imports late due to missing pre-commit/local run wrappers for linting.
- Duplicated `.env` variables and connection string variations across files.

## 3. Preventive controls
- **Make optional via Wrappers**: Created `scripts/dev.ps1` and `scripts/dev.sh` to handle up/down/test/lint with zero Make dependency.
- **Golden-path dev runbook**: Added `docs/runbook/dev.md` explicitly differentiating host vs container targets.
- **Windows boundary rule**: Mapped Windows-incompatible tests (worker RQ tests) with explicit Python `pytest.mark.skipif` targeting `sys.platform == "win32"`.
- **CI Contract Enforcement**: Updated `.github/workflows/ci.yml` with explicit invariant checks (idempotency, schema, budget, send gating).
