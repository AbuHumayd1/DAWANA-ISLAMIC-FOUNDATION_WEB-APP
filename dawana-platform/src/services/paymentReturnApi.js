import { getCsrfToken } from './operationsApi.js'
import { readApiResponse } from './apiResponse.js'

const base = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

async function sessionPost(path, body, token) {
  if (typeof window !== 'undefined' && new URL(base, window.location.href).origin !== window.location.origin) {
    throw new Error('Secure payment recovery requires the same-origin API proxy.')
  }
  const csrf = await getCsrfToken()
  const headers = { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${base}${path}`, {
    method: 'POST', credentials: 'include', cache: 'no-store', headers, body: JSON.stringify(body),
  })
  return readApiResponse(response)
}

export function preparePaymentReturn(orderId, token) {
  return sessionPost(`/dic/orders/${encodeURIComponent(orderId)}/payment-return-grant/`, {}, token)
}

export function resolvePaymentReturn(lookup = {}) {
  return sessionPost('/dic/payments/return/', lookup)
}

export function paymentReturnFailureKind(error) {
  if (error.status === 404) return 'missing'
  if (error.status === 401 || error.status === 403) return 'authorization'
  if (error.status === 429) return 'limited'
  return 'temporary'
}

export function callbackLookup(search, orderId) {
  if (orderId) return { order_id: orderId }
  const params = new URLSearchParams(search)
  const references = [...params.getAll('reference'), ...params.getAll('trxref')]
  if (!references.length) return {}
  if (references.some((value) => !/^[A-Za-z0-9_-]{1,80}$/.test(value) || value !== references[0])) {
    throw new Error('The payment return reference is invalid. Recover the existing registration securely.')
  }
  return { reference: references[0] }
}
