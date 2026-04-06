# Findymail Contact Search Endpoints

This file summarizes the Findymail API endpoints that are most useful for contact search workflows.

Base URL: `https://app.findymail.com`

Authentication:
- Bearer token auth.
- Token is sent with the default security scheme described in `findymail-docs.json`.

Global notes:
- The API docs state a concurrent rate limit of `300` simultaneous requests unless an endpoint says otherwise.
- Common provider failure responses include:
  - `402` for not enough credits
  - `423` for subscription paused

## Recommended primary retrieval

### `POST /api/search/domain`

Purpose:
- Find one or more contacts for a company domain using target roles.
- This is the best first-pass endpoint when we know the account domain and have persona/title hints.

Important behavior:
- Only returns a contact when Findymail found a valid email.
- Synchronous usage is limited to `5` concurrent requests.
- Supports async processing through `webhook_url`.
- Async jobs may take up to `24` hours according to the docs, so synchronous use is simpler for small precision-first workflows.

Request body:
```json
{
  "domain": "company.com",
  "roles": ["CEO", "Founder"],
  "webhook_url": "https://example.com/webhook"
}
```

Required fields:
- `domain`
- `roles`

Field notes:
- `domain`: email domain
- `roles`: array of target roles, max `3`
- `webhook_url`: optional callback URL for async execution

Successful response shape:
```json
{
  "contacts": [
    {
      "domain": "company.com",
      "email": "jane@company.com",
      "name": "jane doe"
    }
  ]
}
```

Usage notes:
- Good for company-domain-driven search when we need candidate emails fast.
- Response data is intentionally sparse: `name`, `email`, and `domain` only.
- Because job title and LinkedIn URL are not returned here, downstream normalization should preserve missing-data flags instead of assuming title or identity certainty.

## Recommended secondary targeted retrieval

### `POST /api/search/name`

Purpose:
- Find a person email from a known full name plus company domain or company name.

Important behavior:
- Uses one finder credit if a verified email is found.
- Supports async mode through `webhook_url`.

Request body:
```json
{
  "name": "Jane Doe",
  "domain": "company.com"
}
```

Required fields:
- `name`
- `domain`

Field notes:
- `name`: full person name
- `domain`: company domain, or company name when needed
- `webhook_url`: optional async callback

Successful response shape:
```json
{
  "contact": {
    "name": "Jane Doe",
    "domain": "company.com",
    "email": "jane@company.com"
  }
}
```

Usage notes:
- Best used when another step already produced a likely person identity.
- Useful as a follow-up resolver after ranking, employee discovery, or manual selection.
- Like `/api/search/domain`, the response is sparse and should not be treated as full-profile enrichment.

### `POST /api/search/business-profile`

Purpose:
- Find a person email from a business profile URL, typically LinkedIn.

Important behavior:
- Uses one finder credit if a verified email is found.
- Synchronous usage is limited to `30` concurrent requests.
- Supports async mode through `webhook_url`.

Request body:
```json
{
  "linkedin_url": "https://linkedin.com/in/janedoe"
}
```

Required fields:
- `linkedin_url`

Field notes:
- `linkedin_url`: full LinkedIn URL or username only
- `webhook_url`: optional async callback

Successful response shape:
```json
{
  "contact": {
    "name": "Jane Doe",
    "domain": "company.com",
    "email": "jane@company.com"
  }
}
```

Usage notes:
- Best when a LinkedIn profile is already known from another provider, a user selection, or stored evidence.
- Strong targeted resolver for turning profile identity into a verified email candidate.

## Optional enrichment after retrieval

### `POST /api/search/reverse-email`

Purpose:
- Look up a business profile from an email address.
- Useful after a candidate email has already been retrieved and we want stronger identity signals.

Important behavior:
- Uses `1` finder credit if a profile is found without profile data.
- Uses `2` finder credits if `with_profile=true` and complete profile data is found.

Request body:
```json
{
  "email": "jane@company.com",
  "with_profile": true
}
```

Required fields:
- `email`

Field notes:
- `email`: work or personal email
- `with_profile`: optional flag for richer profile enrichment

Response shape without profile enrichment:
```json
{
  "linkedin_url": "https://linkedin.com/in/janedoe"
}
```

Response shape with profile enrichment:
```json
{
  "fullName": "Jane Doe",
  "username": "janedoe",
  "headline": "CEO at Example",
  "jobTitle": "CEO",
  "summary": "Summary",
  "city": "City",
  "region": "Region",
  "country": "Country",
  "companyLinkedinUrl": "https://linkedin.com/company/example",
  "companyName": "Example",
  "companyWebsite": "example.com",
  "isPremium": true,
  "isOpenProfile": true,
  "skills": [],
  "jobs": [],
  "educations": [],
  "certificates": []
}
```

Usage notes:
- This is the strongest optional enrichment endpoint for improving merge safety after email retrieval.
- It can add LinkedIn and title evidence that the main search endpoints do not provide.
- The docs also allow a no-match style response where `linkedin_url` can be `null`, so callers should treat enrichment as optional.

## Optional supporting endpoints

### `POST /api/verify`

Purpose:
- Verify an email address.

Request body:
```json
{
  "email": "jane@company.com"
}
```

Important behavior:
- Uses one verifier credit on all attempted verification.
- Returns a plain-text JSON-like payload in the docs example rather than a clean JSON schema.

Example response from docs:
```text
{ "email": "john@example.com", "verified" : true, "provider": "Google" }
```

Usage notes:
- Useful as a defensive validation step for imported or manually entered emails.
- Usually not required immediately after Findymail search endpoints, since those endpoints already describe returning valid or verified email results.

### `GET /api/credits`

Purpose:
- Inspect remaining credits before or during contact-search execution.

Successful response shape:
```json
{
  "credits": 150,
  "verifier_credits": 100
}
```

Usage notes:
- Helpful for provider health checks, diagnostics, and clearer failure summaries.
- `credits` and `verifier_credits` should be handled separately.

## Lower-priority endpoints

### `POST /api/search/employees`

Purpose:
- Find employees by company website and job titles.

Important behavior:
- Uses `1` credit per found contact.
- Does not return email.
- Accepts up to `10` `job_titles`.
- `count` max is `5`.

Example response:
```json
[
  {
    "name": "John Done",
    "linkedinUrl": "https://www.linkedin.com/in/john-doe/",
    "companyWebsite": "https://www.findymail.com",
    "companyName": "Findymail",
    "jobTitle": "Software Engineer"
  }
]
```

Usage notes:
- This is a useful discovery endpoint when we need likely people but do not yet have names.
- It is weaker as a direct contact-search terminal step because it does not provide email.
- It becomes more useful in a multi-step flow such as:
  - discover likely employees
  - resolve a selected person with `/api/search/name` or `/api/search/business-profile`

## Implementation cautions

- Sparse results are normal. The main retrieval endpoints often do not include job title, LinkedIn URL, or other rich identity fields.
- Missing fields should be preserved explicitly rather than guessed.
- Sync concurrency limits differ by endpoint:
  - `/api/search/domain`: `5`
  - `/api/search/business-profile`: `30`
- Async webhook mode exists, but it adds workflow complexity and longer completion times.
- Credit-aware error handling is required for `402` and `423`.
- Provider output should be treated as untrusted until normalized into internal contact models.
