import React, { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { auth } from '@/lib/api'
import AdminPage from '@/pages/AdminPage'
import LoginPage from '@/pages/LoginPage'
import WorkspacePage from '@/pages/WorkspacePage'
import { useAuthStore } from '@/stores/authStore'

function RequireAuth({ children }) {
  const token = useAuthStore((state) => state.token)
  return token ? children : <Navigate to="/login" replace />
}

export default function App() {
  const token = useAuthStore((state) => state.token)
  const setUser = useAuthStore((state) => state.setUser)
  const logout = useAuthStore((state) => state.logout)

  useEffect(() => {
    if (!token) {
      setUser(null)
      return
    }

    auth.me(token)
      .then((me) => {
        setUser({
          userId: me.user_id,
          email: me.email,
          displayName: me.display_name,
          isPlatformAdmin: Boolean(me.is_platform_admin),
          requestId: me.request_id,
        })
      })
      .catch(() => logout())
  }, [logout, setUser, token])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/admin"
          element={(
            <RequireAuth>
              <AdminPage />
            </RequireAuth>
          )}
        />
        <Route
          path="/*"
          element={(
            <RequireAuth>
              <WorkspacePage />
            </RequireAuth>
          )}
        />
      </Routes>
    </BrowserRouter>
  )
}
