import { useQueries } from '@tanstack/react-query'

import { setup, workspace } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { useTenantStore } from '@/stores/tenantStore'

export function useEntityBrowserData() {
  const token = useAuthStore((state) => state.token)
  const activeTenantId = useTenantStore((state) => state.activeTenantId)

  const [
    sellerProfilesQuery,
    icpProfilesQuery,
    accountsQuery,
    contactsQuery,
    workflowRunsQuery,
  ] = useQueries({
    queries: [
      {
        queryKey: ['browser', activeTenantId, 'sellerProfiles'],
        queryFn: () => setup.listSellerProfiles(token, activeTenantId, { limit: 100 }),
        enabled: Boolean(token && activeTenantId),
      },
      {
        queryKey: ['browser', activeTenantId, 'icpProfiles'],
        queryFn: () => setup.listIcpProfiles(token, activeTenantId, { limit: 100 }),
        enabled: Boolean(token && activeTenantId),
      },
      {
        queryKey: ['browser', activeTenantId, 'accounts'],
        queryFn: () => workspace.listAccounts(token, activeTenantId, { limit: 100 }),
        enabled: Boolean(token && activeTenantId),
      },
      {
        queryKey: ['browser', activeTenantId, 'contacts'],
        queryFn: () => workspace.listContacts(token, activeTenantId, { limit: 100 }),
        enabled: Boolean(token && activeTenantId),
      },
      {
        queryKey: ['browser', activeTenantId, 'workflowRuns'],
        queryFn: () => workspace.listWorkflowRuns(token, activeTenantId, { limit: 100 }),
        enabled: Boolean(token && activeTenantId),
      },
    ],
  })

  const queries = [
    sellerProfilesQuery,
    icpProfilesQuery,
    accountsQuery,
    contactsQuery,
    workflowRunsQuery,
  ]

  return {
    loading: queries.some((query) => query.isLoading || query.isFetching),
    error: queries.find((query) => query.error)?.error?.message || '',
    sellerProfiles: sellerProfilesQuery.data?.items || [],
    icpProfiles: icpProfilesQuery.data?.items || [],
    accounts: accountsQuery.data?.items || [],
    contacts: contactsQuery.data?.items || [],
    workflowRuns: workflowRunsQuery.data?.items || [],
    refetchAll: async () => {
      await Promise.all(queries.map((query) => query.refetch()))
    },
  }
}
