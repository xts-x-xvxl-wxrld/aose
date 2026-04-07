import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { completeSignIn } from '@/features/auth/authClient'
import { useAuthStore } from '@/stores/authStore'

export default function AuthCallbackPage() {
  const navigate = useNavigate()
  const setToken = useAuthStore((state) => state.setToken)
  const setAuthStatus = useAuthStore((state) => state.setAuthStatus)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    async function finishSignIn() {
      setAuthStatus('loading')
      try {
        const oidcUser = await completeSignIn()
        if (!active) return
        setToken(oidcUser?.access_token || '')
        setAuthStatus('authenticated')
        navigate(oidcUser?.state?.returnTo || '/workspace', { replace: true })
      } catch (err) {
        if (!active) return
        setAuthStatus('unauthenticated')
        setError(err.message || 'Unable to complete the Zitadel sign-in flow.')
      }
    }

    void finishSignIn()
    return () => {
      active = false
    }
  }, [navigate, setAuthStatus, setToken])

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      <div className="max-w-md rounded-3xl border border-border bg-card p-6 shadow-sm">
        <h1 className="text-xl font-semibold tracking-tight">Completing sign-in</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Restoring your session and loading the workspace.
        </p>
        {error && (
          <p className="mt-4 text-sm text-destructive">{error}</p>
        )}
      </div>
    </div>
  )
}
