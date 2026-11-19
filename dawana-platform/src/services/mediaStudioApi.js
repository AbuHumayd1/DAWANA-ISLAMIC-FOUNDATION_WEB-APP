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

export async function changeStudioPassword(current_password, new_password, confirm_password) {
  await token()
  const apiRoot = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
  const response = await fetch(`${apiRoot}/dic/staff/auth/password/change/`, {
    method: 'POST', credentials: 'include', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
    body: JSON.stringify({ current_password, new_password, confirm_password }),
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
export const studioLibrary = ({ library, q, state, edition, page = 1 }) => {
  const params = new URLSearchParams({ library, page: String(page) })
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

export const studioEdit = (library, id, metadata) => studioRequest(`/library/${encodeURIComponent(library)}/${encodeURIComponent(id)}/metadata/`, { method: 'PATCH', body: metadata })

export const studioAssets = (page = 1, { kind = '', q = '', album = '' } = {}) => {
  const params = new URLSearchParams({ page: String(page) })
  if (kind) params.set('kind', kind)
  if (q) params.set('q', q)
  if (album) params.set('album', album)
  return studioRequest('/assets/?' + params.toString())
}
export const studioLinkAsset = (source_kind, source_id) =>
  studioRequest('/assets/', { method: 'POST', body: { source_kind, source_id } })
export const studioAssetMetadata = (id, fields) =>
  studioRequest(`/assets/${encodeURIComponent(id)}/`, { method: 'PATCH', body: fields })
export const studioArchiveAsset = (id, action) =>
  studioRequest(`/assets/${encodeURIComponent(id)}/`, { method: 'POST', body: { action } })
export const studioPlacement = (id, destination, action, edition = null) =>
  studioRequest(`/assets/${encodeURIComponent(id)}/placements/`, {
    method: 'POST', body: { destination, action, edition },
  })

export const studioHostedLinks = (items) => studioRequest('/hosted-links/', { method: 'POST', body: { items } })
