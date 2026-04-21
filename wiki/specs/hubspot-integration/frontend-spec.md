---
title: HubSpot Integration — Frontend Spec
category: spec
agent: Claude Code
date: 2026-04-21
status: active
sources: []
---

# HubSpot Integration — Frontend Spec

## Summary of new surfaces

1. **Integrations settings page** — connect / disconnect HubSpot
2. **Push button on research results** — appears on Account and Contact cards after research completes
3. **Connection status indicator** — small badge in the nav indicating connected/not

---

## 1. HubSpot connection state

### Global state (Zustand)

Add a `hubspot` slice:

```js
{
  hubspot: {
    connected: false,        // bool
    hubId: null,             // number | null
    loading: false,          // fetching status
    error: null,             // string | null
  }
}
```

Load on app init (after auth resolves):

```js
GET /api/v1/hubspot/status
→ set hubspot.connected and hubspot.hubId
```

### API client additions (`src/lib/api.js`)

```js
hubspot.getStatus()                        // GET /api/v1/hubspot/status
hubspot.getConnectUrl()                    // GET /api/v1/hubspot/connect → returns { auth_url }
hubspot.disconnect()                       // DELETE /api/v1/hubspot/disconnect
hubspot.pushCompany(accountId)             // POST /api/v1/hubspot/push/company
hubspot.pushContact(contactId)             // POST /api/v1/hubspot/push/contact
```

---

## 2. Integrations settings page

**Route:** `/settings/integrations`

### Layout

A simple settings card for HubSpot. No other integrations exist yet — keep the page generic enough to add more later.

```
[HubSpot]
  Logo + "HubSpot CRM"
  Description: "Push researched companies and contacts directly to your HubSpot portal."

  [Not connected]
    Button: "Connect HubSpot"   → calls getConnectUrl(), then window.location.href = auth_url

  [Connected — hub ID 12345678]
    Status chip: "Connected" (green)
    Button: "Disconnect"        → calls disconnect(), updates store
```

### OAuth callback handling

The backend redirects to `/settings/integrations?connected=hubspot` or `?error=hubspot_failed`.

On mount, the page checks `window.location.search`:
- `?connected=hubspot` → re-fetch status, show success toast "HubSpot connected"
- `?error=hubspot_failed` → show error toast "Could not connect HubSpot. Try again."
- Then clean the query string from the URL (`history.replaceState`)

---

## 3. Push button on research result cards

### Where it appears

Push buttons appear on **Account cards** and **Contact cards** in the research results surface, after a workflow run completes. They do not appear on search-only results that have no research summary.

### Button states

```
[Push to HubSpot]           default — not yet pushed
[Pushing…]                  loading — API call in flight
[Saved in HubSpot ↗]        success — link opens HubSpot record in new tab
[Retry push]                error — show error message below button
```

### Behaviour

1. If `hubspot.connected === false`:
   - Clicking "Push to HubSpot" opens a small inline prompt:
     "Connect your HubSpot account first." + "Connect now →" (navigates to `/settings/integrations`)
   - Do not silently fail.

2. If connected:
   - Call `hubspot.pushCompany(accountId)` or `hubspot.pushContact(contactId)`
   - On success: update local card state to `pushed`, store `hubspotUrl` from response
   - On error: show inline error message with the error code (see backend error table)

3. Re-push: if a card was already pushed (`hubspot_company_id` is set), the button still reads "Push to HubSpot" — pushing again updates the record rather than creating a duplicate (backend handles upsert).

### State per card

Track push state locally in component state (not global store):

```js
const [pushState, setPushState] = useState('idle') // idle | loading | success | error
const [hubspotUrl, setHubspotUrl] = useState(null)
const [pushError, setPushError] = useState(null)
```

---

## 4. Connection status indicator

A small indicator in the primary nav (sidebar or top bar, wherever the nav lives):

- **Connected:** small HubSpot logo icon + "HubSpot" label, green dot
- **Not connected:** grey HubSpot logo, no dot
- Clicking either state navigates to `/settings/integrations`

This is a read-only indicator — no inline action.

---

## 5. Navigation / routing additions

| Route | Purpose |
|-------|---------|
| `/settings/integrations` | New page — HubSpot connect/disconnect |

Add to the settings section of the nav. If a settings section doesn't exist yet, create a minimal one with just "Integrations" as the first item.

---

## 6. Error messages shown to users

| Backend error code | User-facing message |
|-------------------|-------------------|
| `hubspot_not_connected` | "Connect HubSpot first in Settings → Integrations." |
| `hubspot_token_expired` | "Your HubSpot connection expired. Reconnect in Settings." |
| `hubspot_unavailable` | "HubSpot is temporarily unavailable. Try again shortly." |
| HTTP 429 | "HubSpot rate limit reached. Wait a moment and try again." |

---

## 7. File layout

```
frontend/src/
  pages/
    SettingsIntegrationsPage.jsx    # /settings/integrations
  components/
    HubSpotConnectCard.jsx          # connect/disconnect card used on settings page
    HubSpotPushButton.jsx           # reusable push button for account/contact cards
    HubSpotStatusBadge.jsx          # nav indicator
  store/
    hubspotSlice.js                 # Zustand slice
  lib/
    api.js                          # add hubspot.* methods here
```
