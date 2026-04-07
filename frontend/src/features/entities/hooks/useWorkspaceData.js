import { useEffect, useMemo } from 'react'
import { useQueries } from '@tanstack/react-query'

import { setup, workspace } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { useTenantStore } from '@/stores/tenantStore'

function normalizePreferredId(items, preferredId, idKey) {
  if (!Array.isArray(items) || items.length === 0) return ''
  if (preferredId && items.some((item) => item?.[idKey] === preferredId)) {
    return preferredId
  }
  return items.length === 1 ? items[0]?.[idKey] || '' : ''
}

export function useWorkspaceData() {
  const token = useAuthStore((state) => state.token)
  const activeTenantId = useTenantStore((state) => state.activeTenantId)
  const getTenantContext = useTenantStore((state) => state.getTenantContext)
  const getTenantResources = useTenantStore((state) => state.getTenantResources)
  const setTenantResources = useTenantStore((state) => state.setTenantResources)
  const updateTenantContext = useTenantStore((state) => state.updateTenantContext)

  const tenantContext = getTenantContext(activeTenantId)
  const tenantResources = getTenantResources(activeTenantId)

  const [
    sellerProfilesQuery,
    icpProfilesQuery,
    workflowRunsQuery,
    accountsQuery,
    contactsQuery,
  ] = useQueries({
    queries: [
      {
        queryKey: ['setup', activeTenantId, 'sellerProfiles'],
        queryFn: () => setup.listSellerProfiles(token, activeTenantId),
        enabled: Boolean(token && activeTenantId),
      },
      {
        queryKey: ['setup', activeTenantId, 'icpProfiles'],
        queryFn: () => setup.listIcpProfiles(token, activeTenantId),
        enabled: Boolean(token && activeTenantId),
      },
      {
        queryKey: ['workspace', activeTenantId, 'workflowRuns'],
        queryFn: () => workspace.listWorkflowRuns(token, activeTenantId),
        enabled: Boolean(token && activeTenantId),
      },
      {
        queryKey: [
          'workspace',
          activeTenantId,
          'accounts',
          tenantContext.activeSellerProfileId,
          tenantContext.activeIcpProfileId,
        ],
        queryFn: () => workspace.listAccounts(token, activeTenantId, {
          sellerProfileId: tenantContext.activeSellerProfileId,
          icpProfileId: tenantContext.activeIcpProfileId,
        }),
        enabled: Boolean(token && activeTenantId),
      },
      {
        queryKey: [
          'workspace',
          activeTenantId,
          'contacts',
          tenantContext.activeAccountId,
        ],
        queryFn: () => workspace.listContacts(token, activeTenantId, {
          accountId: tenantContext.activeAccountId,
        }),
        enabled: Boolean(token && activeTenantId && tenantContext.activeAccountId),
      },
    ],
  })

  const sellerProfiles = sellerProfilesQuery.data?.items || []
  const icpProfiles = icpProfilesQuery.data?.items || []
  const workflowRuns = workflowRunsQuery.data?.items || []
  const accounts = accountsQuery.data?.items || []
  const contacts = contactsQuery.data?.items || []

  useEffect(() => {
    if (!activeTenantId) return

    setTenantResources(activeTenantId, {
      sellerProfiles,
      icpProfiles,
      accounts,
      contacts: tenantContext.activeAccountId ? contacts : [],
      workflowRuns,
    })
  }, [
    accounts,
    activeTenantId,
    contacts,
    icpProfiles,
    sellerProfiles,
    setTenantResources,
    tenantContext.activeAccountId,
    workflowRuns,
  ])

  useEffect(() => {
    if (!activeTenantId) return

    const nextSellerProfileId = normalizePreferredId(
      sellerProfiles,
      tenantContext.activeSellerProfileId,
      'seller_profile_id',
    )
    const nextIcpProfileId = normalizePreferredId(
      icpProfiles,
      tenantContext.activeIcpProfileId,
      'icp_profile_id',
    )

    if (
      nextSellerProfileId !== tenantContext.activeSellerProfileId ||
      nextIcpProfileId !== tenantContext.activeIcpProfileId
    ) {
      updateTenantContext(activeTenantId, {
        activeSellerProfileId: nextSellerProfileId,
        activeIcpProfileId: nextIcpProfileId,
      })
    }
  }, [
    activeTenantId,
    icpProfiles,
    sellerProfiles,
    tenantContext.activeIcpProfileId,
    tenantContext.activeSellerProfileId,
    updateTenantContext,
  ])

  useEffect(() => {
    if (!activeTenantId) return
    const nextAccountId = normalizePreferredId(
      accounts,
      tenantContext.activeAccountId,
      'account_id',
    )
    if (nextAccountId !== tenantContext.activeAccountId) {
      updateTenantContext(activeTenantId, {
        activeAccountId: nextAccountId,
        activeContactId: '',
      })
    }
  }, [
    accounts,
    activeTenantId,
    tenantContext.activeAccountId,
    updateTenantContext,
  ])

  useEffect(() => {
    if (!activeTenantId) return

    if (!tenantContext.activeAccountId) {
      if (tenantContext.activeContactId) {
        updateTenantContext(activeTenantId, { activeContactId: '' })
      }
      return
    }

    const nextContactId = normalizePreferredId(
      contacts,
      tenantContext.activeContactId,
      'contact_id',
    )
    if (nextContactId !== tenantContext.activeContactId) {
      updateTenantContext(activeTenantId, { activeContactId: nextContactId })
    }
  }, [
    activeTenantId,
    contacts,
    tenantContext.activeAccountId,
    tenantContext.activeContactId,
    updateTenantContext,
  ])

  const loading = useMemo(
    () => [
      sellerProfilesQuery,
      icpProfilesQuery,
      workflowRunsQuery,
      accountsQuery,
      contactsQuery,
    ].some((query) => query.isLoading || query.isFetching),
    [accountsQuery, contactsQuery, icpProfilesQuery, sellerProfilesQuery, workflowRunsQuery],
  )

  const error = useMemo(() => {
    const failingQuery = [
      sellerProfilesQuery,
      icpProfilesQuery,
      workflowRunsQuery,
      accountsQuery,
      contactsQuery,
    ].find((query) => query.error)
    return failingQuery?.error?.message || ''
  }, [accountsQuery, contactsQuery, icpProfilesQuery, sellerProfilesQuery, workflowRunsQuery])

  return {
    loading,
    error,
    sellerProfiles: tenantResources.sellerProfiles,
    icpProfiles: tenantResources.icpProfiles,
    accounts: tenantResources.accounts,
    contacts: tenantResources.contacts,
    workflowRuns: tenantResources.workflowRuns,
    refreshBaseResources: async () => {
      await Promise.all([
        sellerProfilesQuery.refetch(),
        icpProfilesQuery.refetch(),
        workflowRunsQuery.refetch(),
      ])
    },
    refreshAccountResources: accountsQuery.refetch,
    refreshContactResources: contactsQuery.refetch,
  }
}
