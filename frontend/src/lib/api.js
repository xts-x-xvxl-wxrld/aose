const API_BASE = import.meta.env?.VITE_API_BASE_URL || '/api/v1'

function authHeader(token) {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function readPayload(response) {
  if (response.status === 204) return null

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return response.json()
  }
  return response.text()
}

export function formatError(payload) {
  if (typeof payload === 'string') return payload
  if (!payload || typeof payload !== 'object') return ''
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((entry) => {
        const path = Array.isArray(entry.loc) ? entry.loc.slice(1).join('.') : ''
        return path ? `${path}: ${entry.msg}` : entry.msg
      })
      .join('\n')
  }
  if (typeof payload.message === 'string') return payload.message
  if (typeof payload.detail === 'string') return payload.detail
  return JSON.stringify(payload)
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  const isForm = options.body instanceof URLSearchParams

  if (!isForm && options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })
  const payload = await readPayload(response)

  if (!response.ok) {
    throw new Error(formatError(payload) || `Request failed: ${response.status}`)
  }

  return payload
}

export const auth = {
  me: (token) => request('/me', { headers: authHeader(token) }),
}

export const identity = {
  listTenants: (token) => request('/tenants', { headers: authHeader(token) }),
}

export const tenancy = {
  createTenant: (token, payload) =>
    request('/tenants', {
      method: 'POST',
      headers: authHeader(token),
      body: JSON.stringify(payload),
    }),
}

export const setup = {
  createSellerProfile: (token, tenantId, payload) =>
    request(`/tenants/${tenantId}/seller-profiles`, {
      method: 'POST',
      headers: authHeader(token),
      body: JSON.stringify(payload),
    }),

  updateSellerProfile: (token, tenantId, sellerProfileId, payload) =>
    request(`/tenants/${tenantId}/seller-profiles/${sellerProfileId}`, {
      method: 'PATCH',
      headers: authHeader(token),
      body: JSON.stringify(payload),
    }),

  createIcpProfile: (token, tenantId, payload) =>
    request(`/tenants/${tenantId}/icp-profiles`, {
      method: 'POST',
      headers: authHeader(token),
      body: JSON.stringify(payload),
    }),

  updateIcpProfile: (token, tenantId, icpProfileId, payload) =>
    request(`/tenants/${tenantId}/icp-profiles/${icpProfileId}`, {
      method: 'PATCH',
      headers: authHeader(token),
      body: JSON.stringify(payload),
    }),
}

export const chat = {
  getThread: (token, tenantId, threadId) =>
    request(`/tenants/${tenantId}/chat/threads/${threadId}`, {
      headers: authHeader(token),
    }),

  listMessages: (token, tenantId, threadId) =>
    request(`/tenants/${tenantId}/chat/threads/${threadId}/messages`, {
      headers: authHeader(token),
    }),

  listEvents: (token, tenantId, { threadId = '', limit = 20, offset = 0 } = {}) => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    if (threadId) params.set('thread_id', threadId)

    return request(`/tenants/${tenantId}/chat/events?${params.toString()}`, {
      headers: authHeader(token),
    })
  },
}

export const admin = {
  getOverview: (token) => request('/admin/overview', { headers: authHeader(token) }),

  listPlatformTenants: (token) => request('/admin/tenants', { headers: authHeader(token) }),

  getTenantOverview: (token, tenantId) =>
    request(`/admin/tenants/${tenantId}/ops/overview`, { headers: authHeader(token) }),

  listRuns: (token, tenantId, { limit = 50, offset = 0, status = '' } = {}) => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    if (status) params.set('status', status)
    return request(`/admin/tenants/${tenantId}/ops/runs?${params.toString()}`, {
      headers: authHeader(token),
    })
  },

  getRun: (token, tenantId, runId) =>
    request(`/admin/tenants/${tenantId}/ops/runs/${runId}`, { headers: authHeader(token) }),

  listRunEvents: (token, tenantId, runId) =>
    request(`/admin/tenants/${tenantId}/ops/runs/${runId}/events`, { headers: authHeader(token) }),

  listLlmCalls: (token, tenantId, { runId = '', limit = 50, offset = 0 } = {}) => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    if (runId) params.set('run_id', runId)
    return request(`/admin/tenants/${tenantId}/ops/llm-calls?${params.toString()}`, {
      headers: authHeader(token),
    })
  },

  listToolCalls: (token, tenantId, { runId = '', limit = 50, offset = 0 } = {}) => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    if (runId) params.set('run_id', runId)
    return request(`/admin/tenants/${tenantId}/ops/tool-calls?${params.toString()}`, {
      headers: authHeader(token),
    })
  },

  listGlobalConfigs: (token) => request('/admin/agent-configs/global', { headers: authHeader(token) }),

  listTenantConfigs: (token, tenantId) =>
    request(`/admin/tenants/${tenantId}/agent-configs`, { headers: authHeader(token) }),

  createGlobalConfigVersion: (token, payload) =>
    request('/admin/agent-configs/global/versions', {
      method: 'POST',
      headers: authHeader(token),
      body: JSON.stringify(payload),
    }),

  createTenantConfigVersion: (token, tenantId, payload) =>
    request(`/admin/tenants/${tenantId}/agent-configs/versions`, {
      method: 'POST',
      headers: authHeader(token),
      body: JSON.stringify(payload),
    }),

  activateConfigVersion: (token, versionId) =>
    request(`/admin/agent-configs/${versionId}/activate`, {
      method: 'POST',
      headers: authHeader(token),
    }),

  rollbackConfigVersion: (token, versionId) =>
    request(`/admin/agent-configs/${versionId}/rollback`, {
      method: 'POST',
      headers: authHeader(token),
    }),

  listAuditLogs: (token, { tenantId = '', limit = 50, offset = 0 } = {}) => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    if (tenantId) params.set('tenant_id', tenantId)
    return request(`/admin/audit-logs?${params.toString()}`, {
      headers: authHeader(token),
    })
  },
}
