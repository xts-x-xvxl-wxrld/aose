# web/AGENT.md — React + TypeScript Frontend

## Current status: scaffold stub

The web module is a placeholder. It has the Vite + React + TypeScript scaffolding in place but no business UI yet. There is no `dev` script in `package.json` — `lint` and `build` are both no-ops (`echo` commands).

Do not add UI features here until an epic CONTRACT explicitly scopes them.

## Stack

| Tool | Version | Purpose |
|------|---------|---------|
| React | (via vite) | UI framework |
| TypeScript | (via tsconfig) | Type safety |
| Vite | (vite.config.ts) | Dev server + bundler |

Configured port: **5173** (Vite default, set in `vite.config.ts`).

## File layout

```
web/
├── src/
│   ├── App.tsx          # Root React component (stub)
│   ├── main.tsx         # React entry point
│   └── vite-env.d.ts    # Vite type shims
├── index.html           # HTML entry
├── package.json         # aose-web v0.1.0 — lint/build are stubs
├── tsconfig.json        # TS config
├── tsconfig.node.json   # Vite TS config
└── vite.config.ts       # Vite config (React plugin, port 5173)
```

## What needs to happen before this is usable

1. Add `"dev": "vite"` to `package.json` scripts.
2. Add `"build": "tsc && vite build"` (replacing the echo stub).
3. Add `"lint": "eslint src"` + eslint config (replacing the echo stub).
4. Install actual dependencies: `react`, `react-dom`, `@vitejs/plugin-react`, `typescript`.

These are deferred to a future epic (Epic C or later).

## CI behaviour

The `web-checks` CI job runs:
1. `npm ci`
2. `npm run lint` (currently a no-op echo)
3. `npm run build` (currently a no-op echo)

CI passes even with stub scripts — this is intentional for Epic A.

## Ownership boundary

Per `docs/system/AGENT_RULES.md` §8: web/ is a separate ownership lane from `api/` and `worker/`. Changes that cross this boundary must be split into separate commits.
