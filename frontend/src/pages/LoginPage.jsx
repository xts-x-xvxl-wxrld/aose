import React, { useState } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuthStore } from '@/stores/authStore'

export default function LoginPage() {
  const token = useAuthStore((state) => state.token)
  const loginAsSubject = useAuthStore((state) => state.loginAsSubject)

  const [subject, setSubject] = useState('dev-user')

  if (token) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen max-w-5xl items-center px-6 py-12">
        <div className="grid w-full gap-8 overflow-hidden rounded-[2rem] border border-border bg-card shadow-sm lg:grid-cols-[1.15fr_0.85fr]">
          <section className="relative overflow-hidden border-b border-border bg-sidebar px-8 py-10 lg:border-b-0 lg:border-r">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(15,23,42,0.08),transparent_42%),linear-gradient(135deg,rgba(148,163,184,0.18),transparent_55%)]" />
            <div className="relative space-y-6">
              <div className="inline-flex items-center rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-medium uppercase tracking-[0.22em] text-muted-foreground">
                Phase 2 Workspace
              </div>
              <div className="space-y-3">
                <h1 className="max-w-xl text-4xl font-semibold tracking-tight text-foreground">
                  Chat-first workflow entry for every tenant workspace.
                </h1>
                <p className="max-w-lg text-sm leading-6 text-muted-foreground">
                  This frontend now targets the tenant-scoped chat backend directly. Use any
                  bearer subject in local development, then pick a tenant and continue inside the
                  shared chat workspace.
                </p>
              </div>
              <div className="grid gap-3 text-sm text-muted-foreground sm:grid-cols-3">
                <ValueCard title="Tenant scoped" body="Thread and run state stays isolated by tenant." />
                <ValueCard title="Durable chat" body="Messages and events reload from backend records." />
                <ValueCard title="Setup aware" body="Seller and ICP setup remain in-product for v1." />
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
                  The backend is using fake auth right now, so the bearer token is just the
                  subject string you want to act as.
                </p>
              </div>

              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault()
                  loginAsSubject(subject)
                }}
              >
                <label className="block space-y-2">
                  <span className="text-sm font-medium text-foreground">Bearer subject</span>
                  <input
                    className="w-full rounded-xl border border-input bg-background px-4 py-3 text-sm outline-none transition focus:border-foreground/30 focus:ring-2 focus:ring-ring/20"
                    value={subject}
                    onChange={(event) => setSubject(event.target.value)}
                    placeholder="dev-user"
                  />
                </label>

                <button
                  type="submit"
                  className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition hover:bg-primary/90"
                >
                  Continue
                </button>
              </form>

              <div className="rounded-2xl border border-border bg-muted/40 px-4 py-4 text-sm text-muted-foreground">
                <p className="font-medium text-foreground">Local default</p>
                <p className="mt-1">
                  Leaving the field as <code>dev-user</code> will match the default development
                  subject configured by the backend.
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
