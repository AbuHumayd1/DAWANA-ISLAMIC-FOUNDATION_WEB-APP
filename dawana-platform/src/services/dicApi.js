const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export class DicApiError extends Error {
  constructor(message, statusCode, body) {
    super(message)
    this.name = 'DicApiError'
    this.statusCode = statusCode
    this.body = body
  }
}

function errorMessage(body, fallback) {
  if (!body || typeof body !== 'object') return fallback
  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && typeof detail.detail === 'string') return detail.detail
  const messages = Object.entries(body)
    .flatMap(([field, value]) => {
      const values = Array.isArray(value) ? value : [value]
      return values.filter((message) => typeof message === 'string').map((message) => `${field}: ${message}`)
    })
  return messages.length ? messages.join(' ') : fallback
}

async function request(path, { method = 'GET', body, accessToken, idempotencyKey } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'omit',
      cache: 'no-store',
    })
  } catch {
    throw new DicApiError('The registration service could not be reached. Check your connection and try again.', 0, null)
  }

  let data = null
  try {
    data = await response.json()
  } catch {
    if (response.ok) throw new DicApiError('The registration service returned an unreadable response.', response.status, null)
  }
  if (!response.ok) {
    throw new DicApiError(errorMessage(data, `The request could not be completed (HTTP ${response.status}).`), response.status, data)
  }
  return data
}

export function getRegistrationOptions() {
  return request('/dic/registration-options/')
}

export function createRegistrationOrder(payload, idempotencyKey) {
  return request('/dic/orders/', {
    method: 'POST',
    body: payload,
    idempotencyKey,
  })
}

export function getRegistrationOrder(orderId, accessToken) {
  return request(`/dic/orders/${encodeURIComponent(orderId)}/`, { accessToken })
}

export function initializePayment(orderId, accessToken) {
  return request(`/dic/orders/${encodeURIComponent(orderId)}/payments/initialize/`, {
    method: 'POST',
    body: {},
    accessToken,
  })
}

export function verifyPayment(orderId, paymentReference, accessToken) {
  return request(
    `/dic/orders/${encodeURIComponent(orderId)}/payments/${encodeURIComponent(paymentReference)}/verify/`,
    {
      method: 'POST',
      body: {},
      accessToken,
    },
  )
}
