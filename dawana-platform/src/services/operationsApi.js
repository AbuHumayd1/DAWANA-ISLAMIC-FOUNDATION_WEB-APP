const apiBase = import.meta.env?.VITE_API_BASE_URL || '/api/v1'
const operationsBase = `${apiBase.replace(/\/$/, '')}/dic/operations`
let csrfToken

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = new Headers(options.headers || {})
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    if (!csrfToken) await getCsrfToken()
    headers.set('X-CSRFToken', csrfToken)
  }

  const response = await fetch(`${operationsBase}${path}`, {
    ...options,
    method,
    headers,
    credentials: 'include',
  })
  if (!response.ok) {
    let message = `Request failed (${response.status}).`
    try {
      const payload = await response.json()
      message = payload.detail || Object.values(payload).flat().join(' ') || message
    } catch {
      // Keep a useful HTTP error when the response is not JSON.
    }
    const error = new Error(message)
    error.status = response.status
    if (response.status === 401 || (response.status === 403 && /authentication credentials|CSRF/i.test(message))) {
      window.dispatchEvent(new Event('operations-session-expired'))
    }
    throw error
  }
  return response
}

export async function getCsrfToken() {
  const response = await fetch(`${operationsBase}/auth/csrf/`, {
    credentials: 'include',
    cache: 'no-store',
  })
  if (!response.ok) throw new Error('Could not initialize secure sign-in.')
  const payload = await response.json()
  csrfToken = payload.csrfToken
  return csrfToken
}

export async function getOperationsUser() {
  const response = await request('/auth/me/')
  return response.json()
}

export async function signIn(username, password) {
  await getCsrfToken()
  const response = await request('/auth/login/', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  await getCsrfToken()
  return response.json()
}

export async function signOut() {
  await request('/auth/logout/', { method: 'POST' })
  csrfToken = undefined
}

export async function getOperationsData(path) {
  const response = await request(path)
  return response.json()
}

export async function downloadOperationsReport({ report, format, filters = {} }) {
  const params = new URLSearchParams({ report, format, ...filters })
  const response = await request(`/reports/download/?${params}`)
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `dic-${report}.${format}`
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
