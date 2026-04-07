# Wiki Schema

Conventions for all agents maintaining this wiki. This is the single source of truth for both build instructions and project reference.

## Directory structure

```
wiki/
  index.md          # catalog of all pages (agents keep this updated)
  log.md            # append-only activity log (agents write here)
  schema.md         # this file

  specs/            # active build instructions and implementation specs
    frontend-rebuild/           # frontend rebuild specs, screens, UX direction (active)
    frontend-enablement-backend-contract.md  # backend contract for frontend (active)
    backend-domain/             # core backend domain model and implementation specs
    chat-orchestration/         # Phase 2: chat-driven orchestrator (complete)
    provider-workflows/         # Phase 3: provider-backed workflows (complete)
    resilience-and-fallbacks/   # Phase 4: resilience, debuggability, fallbacks (mostly complete)
    authentication/             # Zitadel auth setup and backend auth implementation
    admin-system/               # admin system, telemetry, and agent config versioning

  architecture/     # reference docs describing what exists today
    current-app-overview.md     # high-level description of the app as it stands today
    current-app-overview/       # subsystem and workflow reference pages

  features/         # agent-written summaries of completed features
  decisions/        # agent-written ADR-style technical decision records
```

`specs/` is primarily for instructions and implementation specs. `architecture/` is for reference docs that describe the current system.

Use frontmatter `status` to distinguish active from reference:
- `status: active` - this is something to build now
- `status: reference` - this was already built; read to understand the system
- `status: complete` - was active, now fully implemented

`features/` and `decisions/` are agent-maintained and grow over time as work is done.

## Log entry format

Every log entry must start with this prefix pattern so it is grep-parseable:

```
## [YYYY-MM-DD] <type> | Agent: <name> | <title>
```

Types:
- `plan` - agent is about to start a task
- `complete` - agent finished a task
- `update` - agent updated existing wiki pages without new work
- `lint` - agent ran a health-check pass on the wiki

Example:
```
## [2026-04-07] plan | Agent: Claude Code | Rebuild frontend workspace shell
## [2026-04-07] complete | Agent: Claude Code | Rebuild frontend workspace shell
```

## Wiki page format

Every wiki page should have YAML frontmatter:

```yaml
---
title: Page Title
category: spec | feature | decision
agent: Claude Code | Codex | human
date: YYYY-MM-DD
status: active | reference | complete
sources: []   # related files or external links
---
```

Then markdown content. Use `[[wikilinks]]` for cross-references to other pages.

## When to update the wiki

**Before starting non-trivial work:**
1. Read `wiki/specs/frontend-rebuild/` and `wiki/specs/frontend-enablement-backend-contract.md` for active frontend direction
2. Read `wiki/index.md` to see what the other agent has been doing recently
3. Append a `plan` entry to `wiki/log.md`
4. Create a stub page in `wiki/features/` or `wiki/decisions/`

**After completing work:**
1. Update the stub page with what was built, key decisions, and caveats
2. If a spec page is now fully implemented, update its `status: active` -> `status: complete`
3. Update `wiki/index.md` for every page you touched
4. Append a `complete` entry to `wiki/log.md`
5. Cross-link to related spec pages and architecture pages where relevant

**What counts as non-trivial:** new feature, refactor, schema change, new endpoint, new component, architectural decision.

## Rules

- `wiki/log.md` is append-only - never edit entries already written
- Reference pages in `wiki/architecture/` and completed/reference pages in `wiki/specs/` record what was built - correct factual errors only, don't rewrite them
- If current code contradicts an active spec, flag it rather than silently changing either
