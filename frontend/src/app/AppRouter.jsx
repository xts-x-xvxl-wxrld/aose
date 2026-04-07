import React from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { useAuth } from '@/features/auth/useAuth'
import AdminPage from '@/features/admin/pages/AdminPage'
import AuthCallbackPage from '@/features/auth/pages/AuthCallbackPage'
import LoginPage from '@/features/auth/pages/LoginPage'
import DataBrowserPage from '@/features/entities/pages/DataBrowserPage'
import ReviewPage from '@/features/review/pages/ReviewPage'
import WorkspacePage from '@/features/workspace/pages/WorkspacePage'

function RequireAuth({ children }) {
  const location = useLocation()
  const { authStatus, isAuthenticated } = useAuth()

  if (authStatus === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
        <div className="rounded-3xl border border-border bg-card px-6 py-5 shadow-sm">
          <p className="text-sm text-muted-foreground">Restoring session…</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return children
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route
          path="/admin"
          element={(
            <RequireAuth>
              <AdminPage />
            </RequireAuth>
          )}
        />
        <Route
          path="/workspace/data"
          element={(
            <RequireAuth>
              <DataBrowserPage />
            </RequireAuth>
          )}
        />
        <Route
          path="/workspace/review/:runId"
          element={(
            <RequireAuth>
              <ReviewPage />
            </RequireAuth>
          )}
        />
        <Route
          path="/workspace"
          element={(
            <RequireAuth>
              <WorkspacePage />
            </RequireAuth>
          )}
        />
        <Route path="/" element={<Navigate to="/workspace" replace />} />
        <Route path="*" element={<Navigate to="/workspace" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
