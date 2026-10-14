// Thin fetch wrapper for the IRDSS admin control plane. Every call carries the
// operator's X-API-Key and normalizes FastAPI's `detail` field into a real Error.

const BASE_URL = '/api/v1/admin'
const STORAGE_KEY = 'irdss_admin_key'

export function getStoredKey() {
  return localStorage.getItem(STORAGE_KEY) || ''
}

export function setStoredKey(key) {
  localStorage.setItem(STORAGE_KEY, key)
}

export function clearStoredKey() {
  localStorage.removeItem(STORAGE_KEY)
}

// Turns FastAPI's error payloads (string detail, or a 422 validation array) into one message.
function extractDetail(payload, fallback) {
  if (!payload) return fallback
  const { detail } = payload
  if (typeof detail === 'string') {
    const exposesServerInternals = /(sqlalchemy|psycopg|invalid input syntax|\[sql:|background on this error|traceback)/i.test(detail)
    return exposesServerInternals
      ? 'The server could not complete the request. Please check the submitted values and try again.'
      : detail
  }
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
  }
  return fallback
}

async function request(path, { method = 'GET', body, params, key } = {}) {
  const apiKey = key ?? getStoredKey()
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)

  if (params) {
    Object.entries(params).forEach(([name, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(name, value)
      }
    })
  }

  let response
  try {
    response = await fetch(url.toString().replace(window.location.origin, ''), {
      method,
      headers: {
        'X-API-Key': apiKey,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
  } catch {
    throw new Error("Can't reach the IRDSS gateway. Is the FastAPI server running on port 8081?")
  }

  const text = await response.text()
  let payload = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    const error = new Error(extractDetail(payload, `Request failed (HTTP ${response.status}).`))
    error.status = response.status
    throw error
  }

  return payload
}

async function requestMultipart(path, formData, { method = 'POST', key } = {}) {
  const apiKey = key ?? getStoredKey()
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)

  let response
  try {
    response = await fetch(url.toString().replace(window.location.origin, ''), {
      method,
      headers: {
        'X-API-Key': apiKey,
      },
      body: formData,
    })
  } catch {
    throw new Error("Can't reach the IRDSS gateway. Is the FastAPI server running on port 8081?")
  }

  const text = await response.text()
  let payload = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    const error = new Error(extractDetail(payload, `Request failed (HTTP ${response.status}).`))
    error.status = response.status
    throw error
  }

  return payload
}

export const adminApi = {
  // Phase 1: raw key probe — tells the login screen whether to show root bypass,
  // TOTP enrollment (QR), or a plain code prompt.
  login: (apiKey) => request('/login', { method: 'POST', body: { api_key: apiKey } }),
  setup2fa: (apiKey) => request('/2fa/setup', { method: 'POST', key: apiKey }),
  verify2fa: (apiKey, code) => request('/2fa/verify', { method: 'POST', body: { code }, key: apiKey }),

  verifyKey: (key) => request('/me', { key }),
  getStats: () => request('/stats'),

  listReferrals: (params) => request('/referrals', { params }),
  getReferral: (referralId) => request(`/referrals/${encodeURIComponent(referralId)}`),
  cancelReferral: (referralId) =>
    request(`/referrals/${encodeURIComponent(referralId)}/cancel`, { method: 'PATCH' }),

  listFacilities: (params) => request('/facilities', { params }),
  createFacility: (formData) => requestMultipart('/facilities', formData, { method: 'POST' }),
  updateFacility: (id, body) => request(`/facilities/${id}`, { method: 'PATCH', body }),
  deleteFacility: (id) => request(`/facilities/${id}`, { method: 'DELETE' }),
  listCredentials: (params) => request('/credentials', { params }),
  issueFacilityCredentials: (facilityId, body) => request(`/facilities/${facilityId}/credentials`, { method: 'POST', body }),


  // Backward-compatibility aliases
  listHospitals: (params) => request('/facilities', { params }),
  createHospital: (formData) => requestMultipart('/facilities', formData, { method: 'POST' }),
  updateHospital: (id, body) => request(`/facilities/${id}`, { method: 'PATCH', body }),
  deleteHospital: (id) => request(`/facilities/${id}`, { method: 'DELETE' }),

  listApiKeys: (params) => request('/api-keys', { params }),
  createApiKey: (body) => request('/api-keys', { method: 'POST', body }),
  updateApiKey: (id, body) => request(`/api-keys/${id}`, { method: 'PATCH', body }),
  rotateApiKey: (id) => request(`/api-keys/${id}/rotate`, { method: 'POST' }),
  deleteApiKey: (id) => request(`/api-keys/${id}`, { method: 'DELETE' }),

  getHealth: (params) => request('/system/health', { params }),
  getLogs: (params) => request('/system/logs', { params }),
  flushLogs: () => request('/system/logs', { method: 'DELETE' }),
}
