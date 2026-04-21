# Wiki Log

Append-only chronological record of agent activity. Each entry starts with a consistent prefix for easy parsing:

```
grep "^## \[" wiki/log.md | tail -10
```

---

## [2026-04-07] plan | Agent: Codex | Document the current app in the wiki
I am reviewing the frontend, backend, and existing docs to capture what the app currently does.
The goal is to produce a durable architecture page that explains the product surface, system shape, and notable caveats based on the codebase as it exists today.

## [2026-04-07] complete | Agent: Codex | Document the current app in the wiki
Completed `wiki/architecture/current-app-overview.md` with a code-backed description of the current product, including the chat workspace, tenant model, workflows, review/admin surfaces, and current boundaries.
Updated `wiki/index.md` to catalog the page under Architecture and clear it from In Progress.

## [2026-04-07] plan | Agent: Codex | Restructure the current app wiki into subsystem pages
I am splitting the current app overview into a small set of reference spec pages grouped by subsystem, with the top-level overview becoming a short hub page.
The goal is to preserve the current wiki model under `wiki/specs/` while making the current-app documentation easier to navigate and maintain.

## [2026-04-07] complete | Agent: Codex | Restructure the current app wiki into subsystem pages
Split the current-app reference docs into a hub page plus subsystem pages under `wiki/specs/current-app-overview/`, covering auth/tenancy, domain model, workspace surfaces, runtime, providers, admin, workflows, and review.
Updated `wiki/index.md` to catalog the new page set and recorded the wiki refactor in `wiki/features/wiki-current-app-overview-restructure.md`.

## [2026-04-07] plan | Agent: Codex | Move current-app reference docs out of specs
I am moving the current-app overview reference set from `wiki/specs/` into a dedicated `wiki/architecture/` tree so reference architecture docs are separated from active build specs.
This also requires updating the wiki schema, index, and the existing wiki-refactor feature note so the documented structure matches the repo layout.

## [2026-04-07] complete | Agent: Codex | Move current-app reference docs out of specs
Moved the current-app overview hub page and its subsystem pages into `wiki/architecture/` and updated the wiki schema, index, and agent instructions so reference docs are separated from active specs.
Also updated the current-app wiki restructure feature note so it reflects the final architecture-based location.

## [2026-04-21] plan | Agent: Claude Code | Write HubSpot integration specs
Writing backend and frontend specs for HubSpot OAuth connect/disconnect and push-to-CRM flows.
The goal is to define the integration surface clearly enough that both agents can implement independently without ambiguity.
