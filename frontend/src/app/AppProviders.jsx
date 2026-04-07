import React from 'react'
import { QueryClientProvider } from '@tanstack/react-query'

import { queryClient } from '@/app/queryClient'
import AuthProvider from '@/features/auth/AuthProvider'

export default function AppProviders({ children }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {children}
      </AuthProvider>
    </QueryClientProvider>
  )
}
