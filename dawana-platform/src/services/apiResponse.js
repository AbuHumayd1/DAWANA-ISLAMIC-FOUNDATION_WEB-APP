export function httpError(message, status) {
  const error = new Error(message)
  error.status = status
  return error
}

export async function readApiResponse(response) {
  if (response.status === 204) return null
  let data
  try {
    data = await response.json()
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw httpError(response.ok
      ? 'The server returned an unreadable response. Please retry.'
      : `The server could not complete the request (${response.status}). Please retry.`, response.status)
  }
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail
      : data && typeof data === 'object' ? Object.values(data).flat().filter((value) => typeof value === 'string').join(' ') : ''
    throw httpError(message || `Request failed (${response.status}). Please retry.`, response.status)
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
