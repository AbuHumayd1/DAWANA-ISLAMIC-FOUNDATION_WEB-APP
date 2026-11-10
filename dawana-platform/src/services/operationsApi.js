import { readApiResponse, readCsrfToken } from './apiResponse.js'
import { checkInPath } from './checkIn.js'
import { scoringPath } from './houseScoring.js'
import { reportingPath } from './reporting.js'

const apiBase = import.meta.env?.VITE_API_BASE_URL || '/api/v1'
const operationsBase = `${apiBase.replace(/\/$/, '')}/dic/operations`
let csrfToken

export function getReportingExportUrl(values, format) {
  return operationsBase + reportingPath(values, format)
}

export function getScoringPrintUrl(edition, report) {
  if (!['leaderboard', 'history'].includes(report)) throw new Error('Choose a scoring report.')
  return `${operationsBase}${scoringPath(edition)}&print=${report}`
}

export function getFeedbackExportUrl(edition, filters, format) {
  if (!/^[1-9]\d*$/.test(String(edition)) || !['csv','print'].includes(format)) throw new Error('Choose a valid feedback export.')
  const query=new URLSearchParams({ edition:String(edition), ...filters, export:format })
  return `${operationsBase}/feedback/?${query}`
}

export function getCheckInPrintUrl(edition, search = '') {
  return `${operationsBase}${checkInPath(edition, search)}&print=1`
}

async function request(path, options = {}) {
  const { notifySessionExpiry = true, ...fetchOptions } = options
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
    ...fetchOptions,
    method,
    headers,
    credentials: 'include',
  })
  options.signal?.throwIfAborted()
  if (!response.ok) {
    let error
    try { await readApiResponse(response) } catch (failure) { error = failure }
    options.signal?.throwIfAborted()
    const message = error.message
    if (notifySessionExpiry && (response.status === 401 || (response.status === 403 && /authentication credentials|CSRF/i.test(message)))) {
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
  csrfToken = await readCsrfToken(response)
  return csrfToken
}

export async function getOperationsUser() {
  const response = await request('/auth/me/', { notifySessionExpiry: false })
  return readApiResponse(response)
}

export async function signIn(username, password) {
  await getCsrfToken()
  const response = await request('/auth/login/', {
    notifySessionExpiry: false,
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  await getCsrfToken()
  return readApiResponse(response)
}

export async function signOut() {
  await request('/auth/logout/', { method: 'POST' })
  csrfToken = undefined
}

export async function getOperationsData(path, options = {}) {
  const response = await request(path, options)
  return readApiResponse(response)
}

export async function postOperationsData(path, body, options = {}) {
  await getCsrfToken()
  const response = await request(path, { ...options, method: 'POST', body: JSON.stringify(body) })
  return readApiResponse(response)
}

export async function downloadIDBatch(enrollmentIds) {
  const response = await request('/id-printing/export/', {
    method: 'POST', body: JSON.stringify({ enrollment_ids: enrollmentIds }),
  })
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || 'dic-id-cards.pdf'
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
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
