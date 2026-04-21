---
title: HubSpot Integration — API Contract
category: spec
agent: Claude Code
date: 2026-04-21
status: active
sources:
  - https://developers.hubspot.com/docs/api/crm/companies
  - https://developers.hubspot.com/docs/api/crm/contacts
  - https://developers.hubspot.com/docs/api/crm/notes
  - https://developers.hubspot.com/docs/api/oauth/tokens
---

# HubSpot Integration — API Contract

Two surfaces are defined here:

- **Section A** — HubSpot API calls our backend makes (outbound)
- **Section B** — Our own API shapes the frontend consumes (inbound)

All HubSpot API calls use `Authorization: Bearer {access_token}` and `Content-Type: application/json`.
Base URL for HubSpot CRM API: `https://api.hubapi.com`

---

## Section A — HubSpot API calls (outbound)

### A1. OAuth: exchange code for tokens

```
POST https://api.hubapi.com/oauth/v1/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&client_id={HUBSPOT_CLIENT_ID}
&client_secret={HUBSPOT_CLIENT_SECRET}
&redirect_uri={HUBSPOT_REDIRECT_URI}
&code={code}
```

Response:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 1800,
  "token_type": "bearer"
}
```

Store `access_token`, `refresh_token`, and compute `expires_at = now + expires_in`.

### A2. OAuth: refresh access token

```
POST https://api.hubapi.com/oauth/v1/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
&client_id={HUBSPOT_CLIENT_ID}
&client_secret={HUBSPOT_CLIENT_SECRET}
&refresh_token={refresh_token}
```

Response shape identical to A1. Update `access_token` and `expires_at` in DB.

### A3. OAuth: get portal info (called once after connect)

```
GET https://api.hubapi.com/oauth/v1/access-tokens/{access_token}
```

Response (fields we use):
```json
{
  "hub_id": 12345678,
  "hub_domain": "yourportal.hubspot.com",
  "user": "user@example.com"
}
```

Use `hub_id` to construct HubSpot record URLs and store on `HubSpotConnection`.

---

### A4. Companies: search by domain

Used before create to avoid duplicates.

```
POST /crm/v3/objects/companies/search
```

```json
{
  "filterGroups": [
    {
      "filters": [
        {
          "propertyName": "domain",
          "operator": "EQ",
          "value": "acme.com"
        }
      ]
    }
  ],
  "properties": ["name", "domain", "hs_object_id"],
  "limit": 1
}
```

Response:
```json
{
  "total": 1,
  "results": [
    {
      "id": "123456",
      "properties": {
        "name": "Acme Corp",
        "domain": "acme.com",
        "hs_object_id": "123456"
      }
    }
  ]
}
```

If `total === 0`, proceed to create. If `total >= 1`, use `results[0].id` to update.

### A5. Companies: create

```
POST /crm/v3/objects/companies
```

```json
{
  "properties": {
    "name": "Acme Corp",
    "domain": "acme.com",
    "description": "Enterprise software for logistics teams.",
    "city": "New York",
    "country": "US",
    "industry": "TECHNOLOGY",
    "numberofemployees": "150"
  }
}
```

Response:
```json
{
  "id": "123456",
  "properties": { ... },
  "createdAt": "2026-04-21T10:00:00.000Z",
  "updatedAt": "2026-04-21T10:00:00.000Z"
}
```

Use `id` as `hubspot_company_id`.

> Note: `numberofemployees` is sent as a string even though it represents a number — HubSpot's API requires this for this property.

### A6. Companies: update

```
PATCH /crm/v3/objects/companies/{hubspot_company_id}
```

Same `properties` body as create. Only include fields we have data for — omit null/empty fields entirely.

Response shape same as create.

### A7. Contacts: search by email

```
POST /crm/v3/objects/contacts/search
```

```json
{
  "filterGroups": [
    {
      "filters": [
        {
          "propertyName": "email",
          "operator": "EQ",
          "value": "john.doe@acme.com"
        }
      ]
    }
  ],
  "properties": ["firstname", "lastname", "email", "hs_object_id"],
  "limit": 1
}
```

Response shape mirrors A4.

### A8. Contacts: create

```
POST /crm/v3/objects/contacts
```

```json
{
  "properties": {
    "firstname": "John",
    "lastname": "Doe",
    "email": "john.doe@acme.com",
    "jobtitle": "VP of Engineering",
    "phone": "+1 555 123 4567",
    "company": "Acme Corp"
  }
}
```

Response shape mirrors A5. Use `id` as `hubspot_contact_id`.

### A9. Contacts: update

```
PATCH /crm/v3/objects/contacts/{hubspot_contact_id}
```

Same body as create, omit null/empty fields.

---

### A10. Notes: create

Create a note to attach the research summary to the company or contact.

```
POST /crm/v3/objects/notes
```

```json
{
  "properties": {
    "hs_note_body": "[Agentic OSE Research — 2026-04-21]\n\nAcme Corp is a 150-person logistics software company headquartered in New York. Key decision maker: John Doe (VP Engineering). Recent funding: Series B in 2025.",
    "hs_timestamp": "2026-04-21T10:00:00.000Z"
  }
}
```

Response:
```json
{
  "id": "987654",
  "properties": {
    "hs_note_body": "...",
    "hs_timestamp": "..."
  }
}
```

### A11. Associations: link note to company

```
PUT /crm/v3/objects/notes/{note_id}/associations/companies/{company_id}/note_to_company
```

No request body. Returns `200` on success.

### A12. Associations: link note to contact

```
PUT /crm/v3/objects/notes/{note_id}/associations/contacts/{contact_id}/note_to_contact
```

No request body. Returns `200` on success.

---

### A13. OAuth: revoke token (on disconnect)

```
DELETE https://api.hubapi.com/oauth/v1/refresh-tokens/{refresh_token}
```

Returns `204` on success. Fire-and-forget — if this fails, still delete the local connection row.

---

## Section B — Our own API contract (inbound, consumed by frontend)

All endpoints require `Authorization: Bearer {jwt}` (Zitadel user token). Tenant is resolved from the JWT.

---

### B1. `GET /api/v1/hubspot/status`

Response — connected:
```json
{
  "connected": true,
  "hub_id": 12345678
}
```

Response — not connected:
```json
{
  "connected": false,
  "hub_id": null
}
```

---

### B2. `GET /api/v1/hubspot/connect`

Initiates OAuth. Frontend redirects `window.location.href` to the returned URL.

Response:
```json
{
  "auth_url": "https://app.hubspot.com/oauth/authorize?client_id=...&redirect_uri=...&scope=...&state=..."
}
```

---

### B3. `GET /api/v1/hubspot/callback`

Browser-facing redirect endpoint (not called by frontend JS directly). After token exchange:

- Success → `302` redirect to `{FRONTEND_URL}/settings/integrations?connected=hubspot`
- Failure → `302` redirect to `{FRONTEND_URL}/settings/integrations?error=hubspot_failed`

---

### B4. `DELETE /api/v1/hubspot/disconnect`

No request body.

Response `200`:
```json
{ "disconnected": true }
```

---

### B5. `POST /api/v1/hubspot/push/company`

Request:
```json
{ "account_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" }
```

Response `200`:
```json
{
  "hubspot_company_id": "123456",
  "hubspot_url": "https://app.hubspot.com/contacts/12345678/company/123456",
  "created": true
}
```

`created: true` means a new HubSpot record was made. `created: false` means an existing record was updated.

Error responses:

| Status | Body |
|--------|------|
| 400 | `{ "error": "hubspot_not_connected" }` |
| 404 | `{ "error": "account_not_found" }` |
| 400 | `{ "error": "hubspot_token_expired" }` |
| 429 | `{ "error": "hubspot_rate_limited", "retry_after": 30 }` |
| 502 | `{ "error": "hubspot_unavailable" }` |

---

### B6. `POST /api/v1/hubspot/push/contact`

Request:
```json
{ "contact_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" }
```

Response `200`:
```json
{
  "hubspot_contact_id": "789012",
  "hubspot_url": "https://app.hubspot.com/contacts/12345678/contact/789012",
  "created": true
}
```

Error responses same set as B5.

---

## Sequencing: full push flow

For a company push, the backend calls HubSpot in this order:

```
1. get_valid_access_token()        — refresh if needed (A2)
2. search companies by domain      — A4
3a. if found: PATCH company        — A6
3b. if not found: POST company     — A5
4. POST note                       — A10
5. PUT note → company association  — A11
6. persist hubspot_company_id on Account row
```

For a contact push, add after step 3:

```
3c. if account has hubspot_company_id: also associate contact to company
    PUT /crm/v3/objects/contacts/{contact_id}/associations/companies/{company_id}/contact_to_company
```
