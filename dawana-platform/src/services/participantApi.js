import { readApiResponse, readCsrfToken } from './apiResponse.js'

const base = `${(import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')}/dic/participant`

export async function participantRequest(path, body, { signal } = {}) {
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
    if (/participant session has expired/i.test(error.message)) window.dispatchEvent(new Event('participant-session-expired'))
    throw error
  }
}
