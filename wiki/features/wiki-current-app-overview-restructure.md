---
title: Wiki Current App Overview Restructure
category: feature
agent: Codex
date: 2026-04-07
status: complete
sources:
  - wiki/architecture/current-app-overview.md
  - wiki/index.md
  - wiki/schema.md
---

# Wiki Current App Overview Restructure

## Summary

Split the single current-app reference page into a small subsystem-oriented page set while keeping the top-level overview as the landing page.

## What Changed

- Converted the current-app overview into a shorter hub page.
- Added subsystem reference pages for:
  - auth and tenancy
  - domain model
  - workspace surfaces
  - conversation and runtime
  - providers and tools
  - admin ops and runtime config
- Added workflow/reference pages for:
  - account search
  - account research
  - contact search
  - review and approvals
- Added cross-links from the hub page to every detailed page.
- Updated the wiki index to catalog the new page tree.

## Important Decision

The first split landed under `wiki/specs/`, but the wiki was then adjusted so the current-app reference set now lives under `wiki/architecture/`, keeping "what exists" separate from active build specs.

## Result

The current-app reference docs are now easier to navigate by subsystem and live in the more appropriate `wiki/architecture/` tree.
