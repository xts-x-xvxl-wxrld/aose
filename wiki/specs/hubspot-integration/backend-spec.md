---
title: HubSpot Integration — Backend Spec
category: spec
agent: Claude Code
date: 2026-04-21
status: active
sources: []
---

# HubSpot Integration — Backend Spec

## Environment variables required

```
HUBSPOT_CLIENT_ID=
HUBSPOT_CLIENT_SECRET=
HUBSPOT_REDIRECT_URI=https://{api-host}/api/v1/hubspot/callback
FRONTEND_URL=https://{frontend-host}
```

## OAuth scopes

Request these scopes during the authorization redirect:

```
crm.objects.companies.read
crm.objects.companies.write
crm.objects.contacts.read
crm.objects.contacts.write
crm.objects.notes.write
```

## Data model

### New table: `hubspot_connections`

```python
class HubSpotConnection(Base):
    __tablename__ = "hubspot_connections"

    id: UUID (PK)
    tenant_id: UUID (FK → tenants.id, unique)  # one connection per tenant
    hub_id: int                                 # HubSpot portal ID
    access_token: str                           # encrypted at rest
    refresh_token: str                          # encrypted at rest
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
```

One row per tenant. Upsert on reconnect.

### Changes to existing tables

Add nullable columns to `accounts` and `contacts`:

```
accounts.hubspot_company_id: str | null
contacts.hubspot_contact_id: str | null
```

These store the HubSpot object ID after first push, enabling re-push to update rather than create a duplicate.

## Endpoints

### `GET /api/v1/hubspot/connect`

Initiates OAuth. Requires authenticated user (tenant resolved from JWT).

1. Generate a short-lived signed state token containing `tenant_id` (prevent CSRF)
2. Build HubSpot authorization URL:
   `https://app.hubspot.com/oauth/authorize?client_id=...&redirect_uri=...&scope=...&state=...`
3. Return `{ "auth_url": "..." }` — frontend redirects the browser there

### `GET /api/v1/hubspot/callback`

Receives the OAuth redirect from HubSpot. This is a browser-facing redirect, not a JSON endpoint.

1. Validate `state` token → extract `tenant_id`
2. Exchange `code` for tokens via `POST https://api.hubapi.com/oauth/v1/token`
3. Fetch portal info via `GET https://api.hubapi.com/oauth/v1/access-tokens/{token}` → get `hub_id`
4. Upsert `HubSpotConnection` for `tenant_id`
5. Redirect browser to `{FRONTEND_URL}/settings/integrations?connected=hubspot`

On error: redirect to `{FRONTEND_URL}/settings/integrations?error=hubspot_failed`

### `GET /api/v1/hubspot/status`

Returns connection state for the current tenant.

```json
{ "connected": true, "hub_id": 12345678 }
```

or

```json
{ "connected": false }
```

### `DELETE /api/v1/hubspot/disconnect`

Deletes the `HubSpotConnection` row for the current tenant. Optionally revokes the token with HubSpot. Does not clear `hubspot_company_id` / `hubspot_contact_id` from existing records.

### `POST /api/v1/hubspot/push/company`

Push a researched account to HubSpot as a Company object.

Request body:
```json
{ "account_id": "uuid" }
```

Flow:
1. Fetch `Account` + latest research artifact (the research summary text) from DB
2. Get `HubSpotConnection` for tenant — 400 if not connected
3. Refresh token if `expires_at` is within 5 minutes
4. If `account.hubspot_company_id` is set → update existing company via `PATCH /crm/v3/objects/companies/{id}`
5. Else → search HubSpot by domain: `POST /crm/v3/objects/companies/search` with `domain` filter
   - If found: store ID and update
   - If not found: create via `POST /crm/v3/objects/companies`
6. Create a note with research summary and associate to the company
7. Persist `hubspot_company_id` on the `Account` row

Response:
```json
{
  "hubspot_company_id": "123",
  "hubspot_url": "https://app.hubspot.com/contacts/{hub_id}/company/123",
  "created": true
}
```

### `POST /api/v1/hubspot/push/contact`

Push a researched contact to HubSpot as a Contact object.

Request body:
```json
{ "contact_id": "uuid" }
```

Flow mirrors `/push/company`. Search by email instead of domain. If the contact's account has a `hubspot_company_id`, associate the HubSpot contact to that company.

## Field mapping

### Account → HubSpot Company

| Our field | HubSpot property |
|-----------|-----------------|
| `name` | `name` |
| `domain` | `domain` |
| `description` | `description` |
| `city` | `city` |
| `country` | `country` |
| `industry` | `industry` |
| `employee_count` | `numberofemployees` |

### Contact → HubSpot Contact

| Our field | HubSpot property |
|-----------|-----------------|
| `first_name` | `firstname` |
| `last_name` | `lastname` |
| `email` | `email` |
| `title` | `jobtitle` |
| `phone` | `phone` |
| `account.name` | `company` |

### Research note

Both push flows create a HubSpot Note (`hs_note_body`) containing the research summary text. The note is associated to the company or contact object via the Associations API.

Note body prefix: `[Agentic OSE Research — {date}]\n\n{summary}`

## Token refresh

Implement a `get_valid_access_token(tenant_id)` helper that:
- Checks `expires_at`
- If within 5 minutes, calls `POST https://api.hubapi.com/oauth/v1/token` with `grant_type=refresh_token`
- Updates the DB row
- Returns the fresh token

All push endpoints go through this helper before making HubSpot API calls.

## Error handling

| Condition | HTTP response |
|-----------|--------------|
| Tenant not connected | 400 `{ "error": "hubspot_not_connected" }` |
| Account/contact not found | 404 |
| HubSpot API returns 401 | attempt token refresh once; if still 401 → 400 `hubspot_token_expired` |
| HubSpot API returns 429 | 429 with `Retry-After` forwarded |
| HubSpot API 5xx | 502 `hubspot_unavailable` |

## File layout

```
backend/
  app/
    routers/
      hubspot.py          # all /api/v1/hubspot/* routes
    services/
      hubspot_service.py  # push logic, field mapping, upsert
      hubspot_oauth.py    # connect, callback, token refresh
    models/
      hubspot_connection.py
    schemas/
      hubspot.py          # pydantic request/response schemas
  alembic/versions/
    xxxx_add_hubspot_connection.py
    xxxx_add_hubspot_ids_to_accounts_contacts.py
```
