import { getCsrfToken } from './operationsApi.js'

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export class DicApiError extends Error {
  constructor(message, statusCode, body) {
    super(message)
    this.name = 'DicApiError'
    this.statusCode = statusCode
    this.body = body
  }
}

function errorMessage(body, fallback) {
  // DRF nests serializer errors by field and participant index. Only display
  // recognized validation fields, never serialize the response or submitted form.
  const labels = {
    primary_registrant: 'Booking contact', portal_account: 'Account',
    full_name: 'Name', phone: 'Phone', email: 'Email', address: 'Address',
    username: 'Username', password: 'Password', password_confirmation: 'Password confirmation',
    category_id: 'Category', date_of_birth: 'Date of birth', age_declaration: 'Age declaration',
    sex: 'Sex', height_cm: 'Height', weight_kg: 'Weight', academic_status: 'Academic status',
    occupation: 'Occupation', marital_status: 'Marital status', guardian_relationships: 'Guardian declaration',
    child_index: 'Child', guardian_index: 'Guardian', confirmed: 'Confirmation', pricing: 'Pricing',
  }
  const messages = []
  function visit(value, label = '', depth = 0) {
    if (depth > 6 || messages.length >= 8) return
    if (typeof value === 'string') {
      // Invalid-choice messages can echo the supplied value. Do not echo it.
      const text = value.replace(/"[^"\r\n]*" is not a valid choice\./g, 'The selected value is not a valid choice.')
        .replace(/\p{Cc}/gu, ' ').trim().slice(0, 300)
      if (text) messages.push(label ? `${label}: ${text}` : text)
    } else if (Array.isArray(value)) {
      value.slice(0, 8).forEach(item => visit(item, label, depth + 1))
    } else if (value && typeof value === 'object') {
      for (const [field, child] of Object.entries(value)) {
        if (['participants', 'guardian_relationships'].includes(field) && child && typeof child === 'object') {
          // DRF versions return either a positional list or a sparse index map.
          for (const [index, item] of Object.entries(child)) {
            if (messages.length >= 8) break
            const group = field === 'participants' ? 'Participant' : 'Guardian declaration'
            if (/^\d{1,5}$/.test(index)) visit(item, `${group} ${Number(index) + 1}`, depth + 1)
            else if (index === 'non_field_errors') visit(item, group, depth + 1)
          }
        } else if (field === 'detail' || field === 'non_field_errors') {
          visit(child, label, depth + 1)
        } else if (Object.hasOwn(labels, field)) {
          visit(child, [label, labels[field]].filter(Boolean).join(' — '), depth + 1)
        }
      }
    }
  }
  if (body && typeof body === 'object') visit(body)
  return messages.length ? messages.join(' ') : fallback
}

async function request(path, { method = 'GET', body, accessToken, idempotencyKey } = {}, testerRetry = false) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
  if (testerRetry) headers['X-CSRFToken'] = await getCsrfToken()

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: testerRetry ? 'include' : 'omit',
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
  // Retry only a request rejected by the staging gate before any mutation.
  // Production keeps its existing bearer-only request behavior.
  if (!testerRetry && response.status === 403 && data?.code === 'staging_tester_required') {
    return request(path, { method, body, accessToken, idempotencyKey }, true)
  }
  if (!response.ok) {
    throw new DicApiError(errorMessage(data, `The request could not be completed (HTTP ${response.status}).`), response.status, data)
  }
  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    throw new DicApiError('The registration service returned an unreadable response. Recover the existing registration before starting another payment.', response.status, null)
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

export function acceptOrderPricing(orderId, quote, accessToken) {
  return request(`/dic/orders/${encodeURIComponent(orderId)}/pricing/accept/`, {
    method: 'POST',
    body: { quote },
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

export function getRecoveryChannels() {
  return request('/dic/recovery/channels/')
}

export function requestRecoveryCode(channel, contact) {
  return request('/dic/recovery/challenges/', {
    method: 'POST',
    body: { channel, contact },
  })
}

export function resendRecoveryCode(challengeId, channel, contact) {
  return request(`/dic/recovery/challenges/${encodeURIComponent(challengeId)}/resend/`, {
    method: 'POST',
    body: { channel, contact },
  })
}

export function verifyRecoveryCode(challengeId, code) {
  return request(`/dic/recovery/challenges/${encodeURIComponent(challengeId)}/verify/`, {
    method: 'POST',
    body: { code },
  })
}

export function getRecoveryOrders(recoveryGrant) {
  return request('/dic/recovery/orders/', { accessToken: recoveryGrant })
}

export function restoreRecoveredOrder(orderId, recoveryGrant) {
  return request(`/dic/recovery/orders/${encodeURIComponent(orderId)}/restore/`, {
    method: 'POST',
    body: {},
    accessToken: recoveryGrant,
  })
}


export function authorizeFreshRegistration(orderId, credentials) {
  return request(`/dic/orders/${encodeURIComponent(orderId)}/restart-check/`, { method: 'POST', body: credentials })
}
