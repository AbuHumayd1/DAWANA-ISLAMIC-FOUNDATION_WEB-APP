import { readApiResponse, readCsrfToken } from './apiResponse.js'

const base = `${(import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')}/dic/studio`
let csrf

async function token() {
  const response = await fetch(`${base}/auth/csrf/`, { credentials: 'include', cache: 'no-store' })
  csrf = await readCsrfToken(response)
}

async function studioRequest(path, { method = 'GET', body, ...options } = {}) {
  if (method !== 'GET' && !csrf) await token()
  const response = await fetch(base + path, {
    ...options, method, credentials: 'include', cache: 'no-store',
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(method !== 'GET' ? { 'X-CSRFToken': csrf } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  return readApiResponse(response)
}

export const studioSession = () => studioRequest('/auth/me/')
export async function studioLogin(username, password) {
  await token()
  const user = await studioRequest('/auth/login/', { method: 'POST', body: { username, password } })
  await token()
  return user
}
export async function studioLogout() {
  await studioRequest('/auth/logout/', { method: 'POST' })
  csrf = undefined
}
export const studioLibrary = ({ library, q, state, edition }) => {
  const params = new URLSearchParams({ library })
  if (q) params.set('q', q)
  if (state) params.set('state', state)
  if (edition) params.set('edition', edition)
  return studioRequest('/library/?' + params)
}
export const studioPublish = (library, id, action) =>
  studioRequest(`/library/${encodeURIComponent(library)}/${encodeURIComponent(id)}/publication/`, { method: 'POST', body: { action } })

export const studioUploadStatus = () => studioRequest('/uploads/')
export async function studioUpload(library, fields) {
  if (!csrf) await token()
  const body = new FormData()
  body.append('library', library)
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null && value !== '') body.append(key, value)
  }
  const response = await fetch(base + '/uploads/', {
    method: 'POST', body, credentials: 'include', cache: 'no-store',
    headers: { 'X-CSRFToken': csrf },
  })
  return readApiResponse(response)
}
