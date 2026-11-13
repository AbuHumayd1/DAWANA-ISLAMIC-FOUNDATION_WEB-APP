import { readApiResponse, readCsrfToken } from './apiResponse.js'

const base = `${(import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')}/dic/participant`
const inFlight = new Map()
const cooldowns = new Map()
let deliveryCache

const scopeFor = path => path === '/auth/challenges/' ? 'request' : path === '/auth/verify/' ? 'verify' : 'session'

function consume(promise, signal) {
  if (!signal) return promise
  signal.throwIfAborted()
  return new Promise((resolve, reject) => {
    const abort = () => reject(new DOMException('Request cancelled', 'AbortError'))
    signal.addEventListener('abort', abort, { once: true })
    promise.then(value => { if (!signal.aborted) resolve(value) }, error => { if (!signal.aborted) reject(error) })
      .finally(() => signal.removeEventListener('abort', abort))
  })
}

export async function participantRequest(path, body, { signal, notifyExpiry = true } = {}) {
  signal?.throwIfAborted()
  const scope = scopeFor(path)
  const retryAt = cooldowns.get(scope) || 0
  if (Date.now() < retryAt) {
    const error = new Error('Please wait before trying again.')
    error.status = 429; error.retryAt = retryAt
    throw error
  }
  // Share only non-mutating startup requests. No authenticated records or
  // credentials are cached. Consumer cancellation cannot cancel another mount.
  const shared = body === undefined && (path === '/auth/options/' || (['/auth/me/', '/enrollments/'].includes(path) && !notifyExpiry))
  if (shared && inFlight.has(path)) return consume(inFlight.get(path), signal)
  const promise = sendParticipantRequest(path, body, { signal: shared ? undefined : signal, notifyExpiry }).catch(error => {
    if (error.status === 429) cooldowns.set(scope, Math.max(cooldowns.get(scope) || 0, error.retryAt || Date.now() + 60000))
    throw error
  })
  if (!shared) return promise
  inFlight.set(path, promise)
  promise.then(() => inFlight.delete(path), () => inFlight.delete(path))
  return consume(promise, signal)
}

async function sendParticipantRequest(path, body, { signal, notifyExpiry }) {
  const timeout = AbortSignal.timeout(20000)
  const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout
  try {
    return await sendBoundedRequest(path, body, { signal: requestSignal, notifyExpiry })
  } catch (error) {
    if (timeout.aborted && !signal?.aborted) throw new Error('The participant service is taking too long. Please retry.')
    throw error
  }
}

async function sendBoundedRequest(path, body, { signal, notifyExpiry }) {
  const headers = new Headers({ Accept: 'application/json' })
  if (body !== undefined) {
    const csrf = await fetch(`${base}/auth/csrf/`, { credentials: 'include', cache: 'no-store', signal })
    const token = await readCsrfToken(csrf)
    signal?.throwIfAborted()
    headers.set('X-CSRFToken', token)
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${base}${path}`, {
    signal, method: body === undefined ? 'GET' : 'POST', credentials: 'include', cache: 'no-store', headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  try {
    const data = await readApiResponse(response)
    signal?.throwIfAborted()
    return data
  } catch (error) {
    signal?.throwIfAborted()
    if (notifyExpiry && /participant session has expired/i.test(error.message)) window.dispatchEvent(new Event('participant-session-expired'))
    throw error
  }
}

export async function participantDeliveryOptions({ signal, refresh = false } = {}) {
  signal?.throwIfAborted()
  if (!refresh && deliveryCache && Date.now() < deliveryCache.expiresAt) return deliveryCache.channels
  const data = await participantRequest('/auth/options/', undefined, { signal })
  const channels = data.channels
  if (!Array.isArray(channels) || !channels.length
      || new Set(channels.map(channel => channel?.value)).size !== channels.length
      || channels.some(channel => !channel || !['email', 'sms', 'whatsapp'].includes(channel.value)
        || typeof channel.label !== 'string' || typeof channel.available !== 'boolean')) {
    throw new Error('Could not read secure code delivery availability. Please retry.')
  }
  deliveryCache = { channels, expiresAt: Date.now() + 60000 }
  return channels
}
