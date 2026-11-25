export function httpError(message, status) {
  const error = new Error(message)
  error.status = status
  return error
}

function describeValidation(data) {
  if (!data || typeof data !== 'object') return ''
  const errors = data.errors && typeof data.errors === 'object' ? data.errors : data
  const labels = { photograph: 'Image', flyer: 'Flyer', alt_text: 'Image description',
    biography: 'Biography', name: 'Lecturer name', edition: 'Camp year',
    non_field_errors: 'Details', __all__: 'Details' }
  return Object.entries(errors).filter(([key]) => key !== 'errors' && key !== 'detail')
    .flatMap(([key, value]) => {
      const content = Array.isArray(value) ? value : [value]
      return content.filter(item => typeof item === 'string').map(item =>
        (labels[key] || key.replaceAll('_', ' ')) + ': ' + item)
    }).join(' ')
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
      : describeValidation(data)
    throw responseError(response, message || (response.status === 400
      ? 'Please check the information you entered and try again.'
      : response.status === 403 ? 'You do not have permission for this action. Please contact the administrator.'
      : 'We could not complete your request. Please try again.'))
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
