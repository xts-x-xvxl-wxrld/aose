# Screen And Navigation Spec

## Goal

Define the target frontend shape now that the backend supports both chat workflows and user-visible entity reads.

## App shell principle

The product is chat-first, but not chat-only.

That means:

- chat is the central workspace
- data is always accessible without leaving the tenant context
- review and outputs are reachable from both chat and entity surfaces

## Recommended route model

### `/login`

Purpose:

- Zitadel sign-in entry and callback handling

Current state:

- current page is still fake-auth oriented and should be replaced

### `/`

Purpose:

- redirect into active tenant workspace once tenant/session state is resolved

### `/workspace`

Purpose:

- primary chat-first workspace

Primary contents:

- left rail: tenant switcher, setup context, quick entity shortcuts
- center: chat thread
- right rail: event timeline, current outputs, quick actions

### `/workspace/data`

Purpose:

- browse tenant-scoped data without abandoning the chat-first model

Recommended tabs or subroutes:

- sellers
- ICPs
- accounts
- contacts
- workflow runs
- artifacts

### `/workspace/review/:runId`

Purpose:

- focused review flow when a workflow enters `awaiting_review`

Contents:

- run summary
- artifact preview
- evidence list
- approval controls

### `/admin`

Purpose:

- admin and tenant-ops functionality for authorized users

## Recommended navigation model

### Global navigation

- tenant-aware workspace entry
- data browser access
- admin access when authorized

### Workspace-local navigation

- current chat thread
- current seller/ICP/account/contact context
- direct jump from chat outcomes into data detail views
- direct jump from workflow runs into review view

## Screen responsibilities

### Workspace screen

Should own:

- active tenant shell
- current chat context
- current thread display

Should not own:

- all setup CRUD logic inline forever
- full entity browsing tables/detail layouts inline

### Data screen

Should own:

- paginated/filterable entity browsing
- entity detail panels
- jump-to-chat context actions

### Review screen

Should own:

- approval decisions
- evidence inspection
- artifact reading

## UX transitions that should feel first-class

- from seller/ICP selection into chat
- from chat result into account detail
- from account detail into contact list
- from chat event into workflow run detail
- from workflow run into review flow
- from reviewed output back into chat follow-up
