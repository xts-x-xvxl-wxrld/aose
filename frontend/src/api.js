// LEGACY — do not add new calls here. Use src/lib/api.js
const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || '/api'

export function formatApiErrorPayload(payload) {
  if (typeof payload === 'string') {
    return payload
  }

  if (!payload || typeof payload !== 'object') {
    return ''
  }

  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((entry) => {
        if (!entry || typeof entry !== 'object') {
          return String(entry)
        }
        const path = Array.isArray(entry.loc) ? entry.loc.slice(1).join('.') : ''
        return path ? `${path}: ${entry.msg}` : entry.msg
      })
      .join('\n')
  }

  if (typeof payload.detail === 'string') {
    return payload.detail
  }

  if (payload.detail && typeof payload.detail === 'object') {
    return JSON.stringify(payload.detail)
  }

  return JSON.stringify(payload)
}

async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {})
  const isForm = options.body instanceof URLSearchParams

  if (!isForm && options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (response.status === 204) {
    return null
  }

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const detail = formatApiErrorPayload(payload)
    throw new Error(detail ? `${response.status}: ${detail}` : `Request failed with status ${response.status}`)
  }

  return payload
}

function authHeader(token) {
  return {
    Authorization: `Bearer ${token}`,
  }
}

export function registerUser(email, password) {
  return apiRequest('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function loginUser(email, password) {
  return apiRequest('/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      username: email,
      password,
    }),
  })
}

export function listSellers(token) {
  return apiRequest('/sellers/', {
    headers: authHeader(token),
  })
}

export function createSeller(token, name) {
  return apiRequest('/sellers/', {
    method: 'POST',
    headers: authHeader(token),
    body: JSON.stringify({ name }),
  })
}

export function updateSeller(token, sellerId, name) {
  return apiRequest(`/sellers/${sellerId}`, {
    method: 'PUT',
    headers: authHeader(token),
    body: JSON.stringify({ name }),
  })
}

export function deleteSeller(token, sellerId) {
  return apiRequest(`/sellers/${sellerId}`, {
    method: 'DELETE',
    headers: authHeader(token),
  })
}

export function listIcps(token, sellerId) {
  return apiRequest(`/sellers/${sellerId}/icps/`, {
    headers: authHeader(token),
  })
}

export function createIcp(token, sellerId, payload) {
  return apiRequest(`/sellers/${sellerId}/icps/`, {
    method: 'POST',
    headers: authHeader(token),
    body: JSON.stringify(payload),
  })
}

export function updateIcp(token, sellerId, icpId, payload) {
  return apiRequest(`/sellers/${sellerId}/icps/${icpId}`, {
    method: 'PUT',
    headers: authHeader(token),
    body: JSON.stringify(payload),
  })
}

export function deleteIcp(token, sellerId, icpId) {
  return apiRequest(`/sellers/${sellerId}/icps/${icpId}`, {
    method: 'DELETE',
    headers: authHeader(token),
  })
}

export function runCompanySearch(token, sellerId, icpId, payload) {
  return apiRequest(`/sellers/${sellerId}/icps/${icpId}/company-search`, {
    method: 'POST',
    headers: authHeader(token),
    body: JSON.stringify(payload),
  })
}

export function listAccounts(token, sellerId) {
  return apiRequest(`/sellers/${sellerId}/accounts/`, {
    headers: authHeader(token),
  })
}

export function createAccount(token, sellerId, payload) {
  return apiRequest(`/sellers/${sellerId}/accounts/`, {
    method: 'POST',
    headers: authHeader(token),
    body: JSON.stringify(payload),
  })
}

export function deleteAccount(token, sellerId, accountId) {
  return apiRequest(`/sellers/${sellerId}/accounts/${accountId}`, {
    method: 'DELETE',
    headers: authHeader(token),
  })
}

export function startAccountCrawl(token, sellerId, accountId) {
  return apiRequest(`/sellers/${sellerId}/accounts/${accountId}/crawl`, {
    method: 'POST',
    headers: authHeader(token),
  })
}

export function getAccountCrawlStatus(token, sellerId, accountId) {
  return apiRequest(`/sellers/${sellerId}/accounts/${accountId}/crawl`, {
    headers: authHeader(token),
  })
}

export function listAccountPageSnapshots(token, sellerId, accountId) {
  return apiRequest(`/sellers/${sellerId}/accounts/${accountId}/page-snapshots`, {
    headers: authHeader(token),
  })
}

export function listAccountExtractedFacts(token, sellerId, accountId) {
  return apiRequest(`/sellers/${sellerId}/accounts/${accountId}/facts`, {
    headers: authHeader(token),
  })
}

export function searchContacts(token, sellerId, accountId, size = 5) {
  return apiRequest(`/sellers/${sellerId}/contacts/person-search`, {
    method: 'POST',
    headers: authHeader(token),
    body: JSON.stringify({ account_id: accountId, size }),
  })
}

export function listContacts(token, sellerId, accountId) {
  return apiRequest(`/sellers/${sellerId}/contacts/?account_id=${accountId}`, {
    headers: authHeader(token),
  })
}

export function submitChat(token, messages) {
  return apiRequest('/chat/', {
    method: 'POST',
    headers: authHeader(token),
    body: JSON.stringify({ messages }),
  })
}

export function pollChatTask(token, taskId) {
  return apiRequest(`/chat/${taskId}`, {
    headers: authHeader(token),
  })
}
