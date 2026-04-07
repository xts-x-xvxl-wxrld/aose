import { useCallback } from 'react'

import { clearStoredAuthUser, signIn, signOut } from '@/features/auth/authClient'
import { useAuthStore } from '@/stores/authStore'

export function useAuth() {
  const authStatus = useAuthStore((state) => state.authStatus)
  const isConfigured = useAuthStore((state) => state.isConfigured)
  const token = useAuthStore((state) => state.token)
  const user = useAuthStore((state) => state.user)
  const clearSession = useAuthStore((state) => state.clearSession)

  const login = useCallback(async (returnTo = '/workspace') => {
    await signIn(returnTo)
  }, [])

  const logout = useCallback(async () => {
    try {
      await signOut()
    } catch {
      await clearStoredAuthUser()
    } finally {
      clearSession()
    }
  }, [clearSession])

  return {
    authStatus,
    isConfigured,
    isAuthenticated: authStatus === 'authenticated' && Boolean(token),
    token,
    user,
    login,
    logout,
  }
}
