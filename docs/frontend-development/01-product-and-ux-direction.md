# Product And UX Direction

## Fixed product direction

- product flow is chat-first
- users still need direct access to their managed tenant data
- the frontend should read all user-attributed data
- internal operational messaging stays server-side unless explicitly surfaced through admin/debug UX

## Recommended information architecture

### Primary workspace

- center: chat workspace
- side surface: current tenant context and workflow context
- supporting data surface: entity browser for managed records

### User-visible data domains

- seller profiles
- ICP profiles
- accounts
- contacts
- artifacts
- evidence
- reviewable outputs / approvals

## Recommended screen model

- login / auth callback
- tenant selection / tenant entry
- chat workspace
- data browser page or panel
- review drawer or review page
- admin page

## UX principle

Chat starts work.

Entity/data surfaces let the user:

- inspect what already exists
- return to prior workflow outputs
- verify results and evidence
- manage context before sending the next chat turn
