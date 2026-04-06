import { create } from 'zustand'

const ACTIVE_TENANT_KEY = 'ose-active-tenant-id'
const TENANT_CONTEXT_KEY = 'ose-tenant-context'

function loadTenantContext() {
  try {
    return JSON.parse(localStorage.getItem(TENANT_CONTEXT_KEY) || '{}')
  } catch {
    return {}
  }
}

function persistTenantContext(contextByTenant) {
  localStorage.setItem(TENANT_CONTEXT_KEY, JSON.stringify(contextByTenant))
}

function getEmptyTenantContext() {
  return {
    sellerProfiles: [],
    icpProfiles: [],
    activeSellerProfileId: '',
    activeIcpProfileId: '',
    activeAccountId: '',
    activeContactId: '',
    threadId: '',
  }
}

export const useTenantStore = create((set, get) => ({
  tenants: [],
  loading: false,
  error: null,
  activeTenantId: localStorage.getItem(ACTIVE_TENANT_KEY) || '',
  contextByTenant: loadTenantContext(),

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

  upsertSellerProfile: (tenantId, sellerProfile) =>
    set((state) => {
      const currentContext = state.contextByTenant[tenantId] || getEmptyTenantContext()
      const remainingProfiles = currentContext.sellerProfiles.filter(
        (profile) => profile.seller_profile_id !== sellerProfile.seller_profile_id,
      )
      const nextContextByTenant = {
        ...state.contextByTenant,
        [tenantId]: {
          ...currentContext,
          sellerProfiles: [...remainingProfiles, sellerProfile],
          activeSellerProfileId: sellerProfile.seller_profile_id,
        },
      }
      persistTenantContext(nextContextByTenant)
      return { contextByTenant: nextContextByTenant }
    }),

  upsertIcpProfile: (tenantId, icpProfile) =>
    set((state) => {
      const currentContext = state.contextByTenant[tenantId] || getEmptyTenantContext()
      const remainingProfiles = currentContext.icpProfiles.filter(
        (profile) => profile.icp_profile_id !== icpProfile.icp_profile_id,
      )
      const nextContextByTenant = {
        ...state.contextByTenant,
        [tenantId]: {
          ...currentContext,
          icpProfiles: [...remainingProfiles, icpProfile],
          activeIcpProfileId: icpProfile.icp_profile_id,
        },
      }
      persistTenantContext(nextContextByTenant)
      return { contextByTenant: nextContextByTenant }
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

  clearTenantContext: (tenantId) =>
    set((state) => {
      const nextContextByTenant = { ...state.contextByTenant }
      delete nextContextByTenant[tenantId]
      persistTenantContext(nextContextByTenant)
      return { contextByTenant: nextContextByTenant }
    }),

  getActiveTenant: () => {
    const { tenants, activeTenantId } = get()
    return tenants.find((tenant) => tenant.tenant_id === activeTenantId) || null
  },

  getTenantContext: (tenantId) => {
    if (!tenantId) return getEmptyTenantContext()
    return get().contextByTenant[tenantId] || getEmptyTenantContext()
  },
}))
