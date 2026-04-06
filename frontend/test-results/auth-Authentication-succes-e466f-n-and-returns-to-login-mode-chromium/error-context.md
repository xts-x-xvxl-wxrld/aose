# Page snapshot

```yaml
- generic [ref=e5]:
  - generic [ref=e8]:
    - generic [ref=e9]: Phase 2 Workspace
    - generic [ref=e10]:
      - heading "Chat-first workflow entry for every tenant workspace." [level=1] [ref=e11]
      - paragraph [ref=e12]: This frontend now targets the tenant-scoped chat backend directly. Use any bearer subject in local development, then pick a tenant and continue inside the shared chat workspace.
    - generic [ref=e13]:
      - generic [ref=e14]:
        - paragraph [ref=e15]: Tenant scoped
        - paragraph [ref=e16]: Thread and run state stays isolated by tenant.
      - generic [ref=e17]:
        - paragraph [ref=e18]: Durable chat
        - paragraph [ref=e19]: Messages and events reload from backend records.
      - generic [ref=e20]:
        - paragraph [ref=e21]: Setup aware
        - paragraph [ref=e22]: Seller and ICP setup remain in-product for v1.
  - generic [ref=e24]:
    - generic [ref=e25]:
      - paragraph [ref=e26]: Sign In
      - heading "Enter the workspace" [level=2] [ref=e27]
      - paragraph [ref=e28]: The backend is using fake auth right now, so the bearer token is just the subject string you want to act as.
    - generic [ref=e29]:
      - generic [ref=e30]:
        - text: Bearer subject
        - textbox "Bearer subject" [ref=e31]:
          - /placeholder: dev-user
          - text: dev-user
      - button "Continue" [ref=e32] [cursor=pointer]
    - generic [ref=e33]:
      - paragraph [ref=e34]: Local default
      - paragraph [ref=e35]:
        - text: Leaving the field as
        - code [ref=e36]: dev-user
        - text: will match the default development subject configured by the backend.
```