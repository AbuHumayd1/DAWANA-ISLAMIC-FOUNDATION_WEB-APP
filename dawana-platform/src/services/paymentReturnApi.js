import { getCsrfToken } from './operationsApi.js'
import { readApiResponse } from './apiResponse.js'

const base = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

// Keep the existing same-origin deployment and the intended HTTPS sibling-domain
// deployment. This does not configure DNS or make a hostname operational; the API
// still enforces exact CORS/CSRF origins, server-side grants and secure Lax cookies.
export function paymentReturnApiAllowed(apiBase, frontendUrl) {
  try {
    const frontend = new URL(frontendUrl), api = new URL(apiBase, frontend)
    if (api.username || api.password || !['http:', 'https:'].includes(api.protocol)) return false
    if (api.origin === frontend.origin) return true
    return ['https://dawanaislamicfoundation.org', 'https://www.dawanaislamicfoundation.org'].includes(frontend.origin)
      && api.origin === 'https://api.dawanaislamicfoundation.org'
  } catch { return false }
}

async function sessionPost(path, body, token) {
  if (typeof window !== 'undefined' && !paymentReturnApiAllowed(base, window.location.href)) {
    const error = new Error('Secure payment recovery requires the same-origin API or the configured HTTPS DA’WANA API domain. Recover the existing registration; do not pay again.')
    error.code = 'payment_return_origin'
    throw error
  }
  const csrf = await getCsrfToken()
  const headers = { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${base}${path}`, {
    method: 'POST', credentials: 'include', cache: 'no-store', headers, body: JSON.stringify(body),
  })
  return readApiResponse(response)
}

export function paymentReturnSetupMessage(error) {
  // Fixed guidance only: never display raw response bodies, URLs or credentials.
  let reason = 'The secure return service could not complete setup. Keep this tab open and retry.'
  if (error?.code === 'payment_return_origin') {
    reason = 'This checkout requires the approved same-site API configuration. Contact DIC support to restore this existing registration.'
  } else if (error?.status === 403) {
    reason = 'Secure return authorization or CSRF validation was refused. Keep this tab open; check browser cookie access and the approved site origin before retrying.'
  } else if ([401, 404].includes(error?.status)) {
    reason = 'Secure order access is unavailable or expired. Restore this existing registration before continuing.'
  } else if (error?.status === 400) {
    reason = 'The server rejected secure return setup. Contact DIC support to check the server-side return session configuration.'
  } else if (error?.status === 429) {
    reason = 'Secure return setup is temporarily rate limited. Wait before retrying.'
  }
  return 'Your payment attempt is preserved, but secure return setup could not complete. '
    + reason + ' No additional payment attempt will be created by this retry.'
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

export function paymentConfirmed(order) {
  return order?.payment_status === 'paid' && order?.status === 'confirmed'
}

export function processingMessages(order) {
  if (!paymentConfirmed(order)) return []
  const messages = []
  if (order.processing?.housing === 'pending') messages.push('Your payment is confirmed. House allocation is pending. Do not pay again.')
  if (order.processing?.housing === 'review') messages.push('Your payment is confirmed. House allocation needs assistance from the DIC team. Do not pay again.')
  if (['recovery_required', 'delivery_pending', 'verification_required'].includes(order.processing?.portal)) messages.push('Your booking is saved. Ask an authorized DIC administrator to review legacy username access; do not register or pay again.')
  if (order.processing?.portal === 'pending') messages.push('Your payment is confirmed. Portal setup is pending; contact the DIC team if it remains unavailable.')
  return messages
}

export function paystackCheckoutUrl(value) {
  try {
    const url = new URL(value)
    if (url.protocol === 'https:' && url.hostname === 'checkout.paystack.com'
      && !url.username && !url.password && (!url.port || url.port === '443')
      && !url.search && !url.hash && /^\/[A-Za-z0-9_-]+$/.test(url.pathname)) return url.href
  } catch { /* Keep the existing registration; never navigate to an unsafe URL. */ }
  return ''
}
