---
title: HubSpot Integration — Overview
category: spec
agent: Claude Code
date: 2026-04-21
status: active
sources: []
---

# HubSpot Integration

## Goal

Allow users to connect their HubSpot portal and push researched companies and contacts directly into HubSpot CRM — as properly typed records with a research note attached. This is the primary output mechanism for the product.

## Why

The app's research output currently lives only in the internal DB with no path to action. Sales reps and agency users live in HubSpot. Pushing research there closes the loop: find → research → HubSpot record ready to work.

## Scope

- HubSpot OAuth 2.0 connect/disconnect per tenant
- Push a researched account → HubSpot Company object + note
- Push a researched contact → HubSpot Contact object + note
- Upsert logic (search by domain/email before creating)
- Track HubSpot object IDs on our records for re-push

Out of scope for this phase: two-way sync, webhooks, HubSpot Marketplace listing, bulk push.

## Reading order

1. [[api-contract]] — exact HubSpot API payloads and our own endpoint schemas (start here for implementation)
2. [[backend-spec]] — OAuth flow, token model, push endpoints, field mapping, file layout
3. [[frontend-spec]] — connect UX, push button, connection state, routing

## Related specs

- [[specs/backend-domain/core-domain-and-ownership]] — Account and Contact models being extended
- [[specs/frontend-rebuild/screen-and-navigation-spec]] — where connect UI and push buttons live
