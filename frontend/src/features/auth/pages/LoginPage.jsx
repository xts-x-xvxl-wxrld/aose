import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '@/features/auth/useAuth'

export default function LoginPage() {
  const location = useLocation()
  const { authStatus, isAuthenticated, isConfigured, login } = useAuth()

  const returnTo = location.state?.from?.pathname || '/workspace'

  if (isAuthenticated) {
    return <Navigate to={returnTo} replace />
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen max-w-5xl items-center px-6 py-12">
        <div className="grid w-full gap-8 overflow-hidden rounded-[2rem] border border-border bg-card shadow-sm lg:grid-cols-[1.15fr_0.85fr]">
          <section className="relative overflow-hidden border-b border-border bg-sidebar px-8 py-10 lg:border-b-0 lg:border-r">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(15,23,42,0.08),transparent_42%),linear-gradient(135deg,rgba(148,163,184,0.18),transparent_55%)]" />
            <div className="relative space-y-6">
              <div className="inline-flex items-center rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-medium uppercase tracking-[0.22em] text-muted-foreground">
                Zitadel Auth
              </div>
              <div className="space-y-3">
                <h1 className="max-w-xl text-4xl font-semibold tracking-tight text-foreground">
                  Chat-first workflow entry for every tenant workspace.
                </h1>
                <p className="max-w-lg text-sm leading-6 text-muted-foreground">
                  Sign in through Zitadel to access your tenant-scoped workspace, managed entities,
                  and review flows.
                </p>
              </div>
              <div className="grid gap-3 text-sm text-muted-foreground sm:grid-cols-3">
                <ValueCard title="Tenant scoped" body="Workspace state remains isolated by tenant membership." />
                <ValueCard title="Durable data" body="Chat, setup, and entity records reload from backend state." />
                <ValueCard title="Review ready" body="User-visible workflow outputs and approvals stay connected." />
              </div>
            </div>
          </section>

          <section className="px-8 py-10">
            <div className="mx-auto max-w-md space-y-6">
              <div className="space-y-2">
                <p className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  Sign In
                </p>
                <h2 className="text-2xl font-semibold tracking-tight">Enter the workspace</h2>
                <p className="text-sm text-muted-foreground">
                  Authentication now uses Zitadel with an OIDC redirect flow.
                </p>
              </div>

              {!isConfigured && (
                <div className="rounded-2xl border border-destructive/20 bg-destructive/10 px-4 py-4 text-sm text-destructive">
                  Zitadel is not configured for this frontend yet. Set the `VITE_ZITADEL_*`
                  variables before using the production auth flow.
                </div>
              )}

              <button
                type="button"
                disabled={!isConfigured || authStatus === 'loading'}
                onClick={() => login(returnTo)}
                className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {authStatus === 'loading' ? 'Checking session…' : 'Continue with Zitadel'}
              </button>

              <div className="rounded-2xl border border-border bg-muted/40 px-4 py-4 text-sm text-muted-foreground">
                <p className="font-medium text-foreground">Redirect flow</p>
                <p className="mt-1">
                  After authentication, the app restores your session and redirects you back into
                  the tenant workspace.
                </p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function ValueCard({ title, body }) {
  return (
    <div className="rounded-2xl border border-border bg-background/75 p-4">
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{body}</p>
    </div>
  )
}
