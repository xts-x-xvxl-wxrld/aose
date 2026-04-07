import React, { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

import { auth } from '@/lib/api'
import { clearStoredAuthUser, getStoredAuthUser } from '@/features/auth/authClient'
import { isZitadelConfigured } from '@/features/auth/authConfig'
import { useAuthStore } from '@/stores/authStore'

export default function AuthProvider({ children }) {
  const token = useAuthStore((state) => state.token)
  const setConfigured = useAuthStore((state) => state.setConfigured)
  const setAuthStatus = useAuthStore((state) => state.setAuthStatus)
  const setToken = useAuthStore((state) => state.setToken)
  const setUser = useAuthStore((state) => state.setUser)
  const clearSession = useAuthStore((state) => state.clearSession)

  useEffect(() => {
    let cancelled = false

    setConfigured(isZitadelConfigured)

    if (!isZitadelConfigured) {
      setToken('')
      setUser(null)
      setAuthStatus('unauthenticated')
      return undefined
    }

    setAuthStatus('loading')
    getStoredAuthUser()
      .then((oidcUser) => {
        if (cancelled) return
        if (oidcUser?.access_token && !oidcUser.expired) {
          setToken(oidcUser.access_token)
          setAuthStatus('authenticated')
          return
        }
        setToken('')
        setUser(null)
        setAuthStatus('unauthenticated')
      })
      .catch(() => {
        if (cancelled) return
        setToken('')
        setUser(null)
        setAuthStatus('unauthenticated')
      })

    return () => {
      cancelled = true
    }
  }, [setAuthStatus, setConfigured, setToken, setUser])

  const meQuery = useQuery({
    queryKey: ['auth', 'me', token],
    queryFn: () => auth.me(token),
    enabled: Boolean(token),
    retry: false,
  })

  useEffect(() => {
    if (!meQuery.data) return

    const me = meQuery.data
    setUser({
      userId: me.user_id,
      email: me.email,
      displayName: me.display_name,
      isPlatformAdmin: Boolean(me.is_platform_admin),
      requestId: me.request_id,
    })
    setAuthStatus('authenticated')
  }, [meQuery.data, setAuthStatus, setUser])

  useEffect(() => {
    if (!meQuery.error) return

    async function resetSession() {
      await clearStoredAuthUser()
      clearSession()
    }

    void resetSession()
  }, [clearSession, meQuery.error])

  return children
}
