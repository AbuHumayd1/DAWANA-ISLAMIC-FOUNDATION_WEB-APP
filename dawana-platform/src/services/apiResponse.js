export function httpError(message, status) {
  const error = new Error(message)
  error.status = status
  return error
}

function responseError(response, message) {
  const error = httpError(message, response.status)
  if (response.status === 429) {
    const header = response.headers.get('Retry-After')
    const seconds = header !== null && /^\d+(?:\.\d+)?$/.test(header.trim()) ? Number(header) : null
    const date = header && seconds === null ? Date.parse(header) : NaN
    const stated = message.match(/available in\s+(\d+)\s+seconds?/i)
    error.retryAt = seconds !== null ? Date.now() + Math.ceil(seconds * 1000)
      : Number.isFinite(date) ? Math.max(Date.now(), date)
      : Date.now() + (stated ? Number(stated[1]) : 60) * 1000
  }
  return error
}

export async function readApiResponse(response) {
  if (response.status === 204) return null
  let data
  try {
    data = await response.json()
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw responseError(response, response.ok
      ? 'The server returned an unreadable response. Please retry.'
      : `The server could not complete the request (${response.status}). Please retry.`)
  }
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail
      : data && typeof data === 'object' ? Object.values(data).flat().filter((value) => typeof value === 'string').join(' ') : ''
    throw responseError(response, message || `Request failed (${response.status}). Please retry.`)
  }
  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    throw httpError('The server returned an unexpected response. Please retry.', response.status)
  }
  return data
}

export async function readCsrfToken(response) {
  const data = await readApiResponse(response)
  if (typeof data?.csrfToken !== 'string' || !data.csrfToken) {
    throw httpError('Could not initialize secure access. Please retry.', response.status)
  }
  return data.csrfToken
}
