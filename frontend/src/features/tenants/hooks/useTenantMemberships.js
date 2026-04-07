import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

import { identity } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { useTenantStore } from '@/stores/tenantStore'

export function useTenantMemberships() {
  const token = useAuthStore((state) => state.token)
  const setLoading = useTenantStore((state) => state.setLoading)
  const setError = useTenantStore((state) => state.setError)
  const setTenants = useTenantStore((state) => state.setTenants)

  const tenantsQuery = useQuery({
    queryKey: ['identity', 'tenants', token],
    queryFn: () => identity.listTenants(token),
    enabled: Boolean(token),
    staleTime: 30000,
  })

  useEffect(() => {
    setLoading(Boolean(token) && (tenantsQuery.isLoading || tenantsQuery.isFetching))
  }, [setLoading, tenantsQuery.isFetching, tenantsQuery.isLoading, token])

  useEffect(() => {
    if (!token) {
      setTenants([])
      return
    }

    if (!tenantsQuery.data) return
    setTenants(tenantsQuery.data.tenants || [])
  }, [setTenants, tenantsQuery.data, token])

  useEffect(() => {
    setError(tenantsQuery.error?.message || null)
  }, [setError, tenantsQuery.error])

  return {
    tenants: tenantsQuery.data?.tenants || [],
    isLoading: tenantsQuery.isLoading || tenantsQuery.isFetching,
    error: tenantsQuery.error?.message || '',
    refetch: tenantsQuery.refetch,
  }
}
