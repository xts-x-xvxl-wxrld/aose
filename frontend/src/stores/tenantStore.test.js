import { beforeEach, describe, expect, test } from 'vitest'

import { useTenantStore } from './tenantStore'

describe('tenantStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useTenantStore.setState({
      tenants: [],
      loading: false,
      error: null,
      activeTenantId: '',
      contextByTenant: {},
    })
  })

  test('auto-selects the only tenant returned by identity lookup', () => {
    useTenantStore.getState().setTenants([
      { tenant_id: 'tenant-1', tenant_name: 'Tenant One', role: 'owner', status: 'active' },
    ])

    expect(useTenantStore.getState().activeTenantId).toBe('tenant-1')
  })

  test('persists locally created setup context per tenant', () => {
    useTenantStore.getState().upsertSellerProfile('tenant-1', {
      seller_profile_id: 'seller-1',
      name: 'Primary seller',
    })
    useTenantStore.getState().updateTenantContext('tenant-1', {
      activeAccountId: 'account-1',
      threadId: 'thread-1',
    })

    const context = useTenantStore.getState().getTenantContext('tenant-1')

    expect(context.activeSellerProfileId).toBe('seller-1')
    expect(context.activeAccountId).toBe('account-1')
    expect(context.threadId).toBe('thread-1')
    expect(context.sellerProfiles).toHaveLength(1)
  })
})
