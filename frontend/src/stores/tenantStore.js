import { create } from 'zustand'

const ACTIVE_TENANT_KEY = 'ose-active-tenant-id'
const TENANT_CONTEXT_KEY = 'ose-tenant-context'

function loadTenantContext() {
  try {
    const rawValue = JSON.parse(localStorage.getItem(TENANT_CONTEXT_KEY) || '{}')
    const normalized = {}

    for (const [tenantId, context] of Object.entries(rawValue || {})) {
      if (!context || typeof context !== 'object') continue
      normalized[tenantId] = {
        activeSellerProfileId: context.activeSellerProfileId || '',
        activeIcpProfileId: context.activeIcpProfileId || '',
        activeAccountId: context.activeAccountId || '',
        activeContactId: context.activeContactId || '',
        threadId: context.threadId || '',
      }
    }

    return normalized
  } catch {
    return {}
  }
}

function persistTenantContext(contextByTenant) {
  localStorage.setItem(TENANT_CONTEXT_KEY, JSON.stringify(contextByTenant))
}

function getEmptyTenantContext() {
  return {
    activeSellerProfileId: '',
    activeIcpProfileId: '',
    activeAccountId: '',
    activeContactId: '',
    threadId: '',
  }
}

function getEmptyTenantResources() {
  return {
    sellerProfiles: [],
    icpProfiles: [],
    accounts: [],
    contacts: [],
    workflowRuns: [],
  }
}

export const useTenantStore = create((set, get) => ({
  tenants: [],
  loading: false,
  error: null,
  activeTenantId: localStorage.getItem(ACTIVE_TENANT_KEY) || '',
  contextByTenant: loadTenantContext(),
  resourcesByTenant: {},

  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  setTenants: (tenants) =>
    set((state) => {
      const nextTenants = Array.isArray(tenants) ? tenants : []
      const activeStillExists = nextTenants.some((tenant) => tenant.tenant_id === state.activeTenantId)
      const nextActiveTenantId = activeStillExists
        ? state.activeTenantId
        : nextTenants.length === 1
          ? nextTenants[0].tenant_id
          : ''

      if (nextActiveTenantId) {
        localStorage.setItem(ACTIVE_TENANT_KEY, nextActiveTenantId)
      } else {
        localStorage.removeItem(ACTIVE_TENANT_KEY)
      }

      return {
        tenants: nextTenants,
        activeTenantId: nextActiveTenantId,
        error: null,
      }
    }),

  selectTenant: (tenantId) => {
    const nextTenantId = tenantId || ''
    if (nextTenantId) {
      localStorage.setItem(ACTIVE_TENANT_KEY, nextTenantId)
    } else {
      localStorage.removeItem(ACTIVE_TENANT_KEY)
    }
    set({ activeTenantId: nextTenantId, error: null })
  },

  setTenantResources: (tenantId, resources) =>
    set((state) => {
      const currentResources = state.resourcesByTenant[tenantId] || getEmptyTenantResources()
      return {
        resourcesByTenant: {
          ...state.resourcesByTenant,
          [tenantId]: {
            ...currentResources,
            ...resources,
          },
        },
      }
    }),

  upsertSellerProfile: (tenantId, sellerProfile) =>
    set((state) => {
      const currentContext = state.contextByTenant[tenantId] || getEmptyTenantContext()
      const currentResources = state.resourcesByTenant[tenantId] || getEmptyTenantResources()
      const remainingProfiles = currentResources.sellerProfiles.filter(
        (profile) => profile.seller_profile_id !== sellerProfile.seller_profile_id,
      )
      const nextContextByTenant = {
        ...state.contextByTenant,
        [tenantId]: {
          ...currentContext,
          activeSellerProfileId: sellerProfile.seller_profile_id,
        },
      }
      persistTenantContext(nextContextByTenant)
      return {
        contextByTenant: nextContextByTenant,
        resourcesByTenant: {
          ...state.resourcesByTenant,
          [tenantId]: {
            ...currentResources,
            sellerProfiles: [...remainingProfiles, sellerProfile],
          },
        },
      }
    }),

  upsertIcpProfile: (tenantId, icpProfile) =>
    set((state) => {
      const currentContext = state.contextByTenant[tenantId] || getEmptyTenantContext()
      const currentResources = state.resourcesByTenant[tenantId] || getEmptyTenantResources()
      const remainingProfiles = currentResources.icpProfiles.filter(
        (profile) => profile.icp_profile_id !== icpProfile.icp_profile_id,
      )
      const nextContextByTenant = {
        ...state.contextByTenant,
        [tenantId]: {
          ...currentContext,
          activeIcpProfileId: icpProfile.icp_profile_id,
        },
      }
      persistTenantContext(nextContextByTenant)
      return {
        contextByTenant: nextContextByTenant,
        resourcesByTenant: {
          ...state.resourcesByTenant,
          [tenantId]: {
            ...currentResources,
            icpProfiles: [...remainingProfiles, icpProfile],
          },
        },
      }
    }),

  updateTenantContext: (tenantId, changes) =>
    set((state) => {
      const currentContext = state.contextByTenant[tenantId] || getEmptyTenantContext()
      const nextContextByTenant = {
        ...state.contextByTenant,
        [tenantId]: {
          ...currentContext,
          ...changes,
        },
      }
      persistTenantContext(nextContextByTenant)
      return { contextByTenant: nextContextByTenant }
    }),

  clearTenantResources: (tenantId) =>
    set((state) => {
      const nextResourcesByTenant = { ...state.resourcesByTenant }
      delete nextResourcesByTenant[tenantId]
      return { resourcesByTenant: nextResourcesByTenant }
    }),

  clearTenantContext: (tenantId) =>
    set((state) => {
      const nextContextByTenant = { ...state.contextByTenant }
      const nextResourcesByTenant = { ...state.resourcesByTenant }
      delete nextContextByTenant[tenantId]
      delete nextResourcesByTenant[tenantId]
      persistTenantContext(nextContextByTenant)
      return {
        contextByTenant: nextContextByTenant,
        resourcesByTenant: nextResourcesByTenant,
      }
    }),

  getActiveTenant: () => {
    const { tenants, activeTenantId } = get()
    return tenants.find((tenant) => tenant.tenant_id === activeTenantId) || null
  },

  getTenantContext: (tenantId) => {
    if (!tenantId) return getEmptyTenantContext()
    return get().contextByTenant[tenantId] || getEmptyTenantContext()
  },

  getTenantResources: (tenantId) => {
    if (!tenantId) return getEmptyTenantResources()
    return get().resourcesByTenant[tenantId] || getEmptyTenantResources()
  },
}))
