# Codex Agent Instructions

## Wiki Protocol

This project uses `wiki/` as the single source of truth for both build instructions and reference. There is no `docs/` directory. You are **Codex**.

Follow the full schema in [wiki/schema.md](wiki/schema.md).

### Where to look before starting work

| What | Where |
|------|-------|
| Active frontend build instructions | `wiki/specs/frontend-rebuild/` |
| Backend contract for the frontend | `wiki/specs/frontend-enablement-backend-contract.md` |
| What the other agent (Claude Code) has been doing | `wiki/index.md` -> In Progress section |
| Current reference architecture and app shape | `wiki/architecture/` |
| How the backend domain works | `wiki/specs/backend-domain/` |
| Chat and orchestration layer | `wiki/specs/chat-orchestration/` |
| Provider-backed workflows | `wiki/specs/provider-workflows/` |
| Resilience and fallback behavior | `wiki/specs/resilience-and-fallbacks/` |
| Auth setup | `wiki/specs/authentication/` |
| Admin system | `wiki/specs/admin-system/` |

Pages with `status: active` in their frontmatter are current build instructions. Pages with `status: reference` are historical records of completed work. In general, active build guidance belongs in `wiki/specs/`, while current-system reference docs belong in `wiki/architecture/`.

### Before starting non-trivial work
1. Read the relevant spec pages in `wiki/specs/`
2. Read `wiki/index.md` to see recent activity from the other agent
3. Append a `plan` entry to `wiki/log.md`:
   ```
   ## [YYYY-MM-DD] plan | Agent: Codex | <what you're about to do>
   <1-3 sentences describing the goal and approach>
   ```
4. Create a stub page under `wiki/features/` or `wiki/decisions/`

### After completing work
1. Update the stub page with what was actually built, key decisions, and caveats
2. If a spec page is now fully implemented, set its frontmatter `status: active` -> `status: complete`
3. Update `wiki/index.md` for every wiki page you touched
4. Append a `complete` entry to `wiki/log.md`:
   ```
   ## [YYYY-MM-DD] complete | Agent: Codex | <what you built>
   <1-3 sentences summarizing what was done and linking to the wiki page>
   ```

### Rules
- `wiki/log.md` is append-only - never edit entries already written
- Reference pages in `wiki/architecture/` and reference/completed spec pages record what was built - correct factual errors only, don't rewrite them
- If current code contradicts an active spec, flag it rather than silently changing either
