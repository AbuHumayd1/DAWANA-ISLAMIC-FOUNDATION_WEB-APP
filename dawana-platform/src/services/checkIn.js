export function checkInPath(edition = '', search = '', page = 1, view = 'active') {
  if (edition && !/^[1-9]\d*$/.test(String(edition))) throw new Error('Choose a valid camp edition.')
  if (!Number.isInteger(page) || page < 1) throw new Error('Choose a valid page.')
  if (search.length > 200) throw new Error('Search must be 200 characters or fewer.')
  if (!['active', 'history'].includes(view)) throw new Error('Choose active or history.')
  const query = new URLSearchParams({ page: String(page) })
  if (view !== 'active') query.set('view', view)
  if (edition) query.set('edition', edition)
  if (search.trim()) query.set('search', search.trim())
  return `/check-in/?${query}`
}

export function checkInTime(value) {
  return value ? new Intl.DateTimeFormat('en-NG', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Lagos' }).format(new Date(value)) : ''
}
