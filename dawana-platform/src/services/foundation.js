import { readApiResponse, readCsrfToken } from './apiResponse.js'
const base = `${(import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')}/foundation`

export async function foundationRequest(path, { body, token, signal } = {}) {
  const headers = {}
  if (body !== undefined) {
    headers['X-CSRFToken'] = await readCsrfToken(await fetch(base + '/csrf/', { credentials: 'include', signal }))
    headers['Content-Type'] = 'application/json'
  }
  if (token) headers['X-Donation-Token'] = token
  return readApiResponse(await fetch(base + path, { method: body === undefined ? 'GET' : 'POST',
    credentials: 'include', headers, signal, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) }))
}

export function safeDonationCheckout(value) {
  try { const url = new URL(value); return url.protocol === 'https:' && url.hostname === 'checkout.paystack.com' && !url.username && !url.password && ['', '443'].includes(url.port) } catch { return false }
}

export function newDonationRequest(email, amount) {
  const bytes = crypto.getRandomValues(new Uint8Array(32))
  return { request_id: crypto.randomUUID(), access_token: [...bytes].map(value => value.toString(16).padStart(2, '0')).join(''), email, amount }
}

export function donationMessage(status) {
  return { successful: 'Thank you. Your donation has been verified.', failed: 'Payment failed. No successful donation is recorded.',
    abandoned: 'Checkout was abandoned. No successful donation is recorded.', pending: 'Payment is pending verification.',
    initializing: 'Initialization is pending. Check this request before attempting another payment.',
    review: 'This payment needs review. Do not pay again for this request.', created: 'Donation request prepared.' }[status] || 'Donation status is unavailable.'
}
