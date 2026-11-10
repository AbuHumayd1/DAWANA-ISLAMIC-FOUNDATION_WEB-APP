// Presentation validation only. Backend models/services remain authoritative.
export function managementPath(resource, edition, filters = {}) {
  if (!/^[1-9]\d*$/.test(String(edition))) throw new Error('Choose a camp edition.')
  if (!/^\/(?:classes\/(?:[1-9]\d*\/)?|class-assignments\/|announcements\/(?:[1-9]\d*\/(?:publication\/)?)?|camp-management\/(?:classes|announcements)\/history\/)$/.test(resource)) throw new Error('Unknown camp management resource.')
  const query = new URLSearchParams({ edition: String(edition) })
  for (const [key, value] of Object.entries(filters)) if (value !== '' && value !== undefined) query.set(key, String(value))
  // Never let caller filters override the selected edition.
  query.set('edition', String(edition))
  return `${resource}?${query}`
}

export function localDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) throw new Error('Invalid announcement time.')
  const two = number => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}T${two(date.getHours())}:${two(date.getMinutes())}:${two(date.getSeconds())}`
}

export function draftPayload(values, row) {
  const title = values.title.trim(), body = values.body.trim()
  if (!title || title.length > 160 || !body || body.length > 5000) throw new Error('Enter a title (up to 160 characters) and content (up to 5,000 characters).')
  const time = value => {
    if (!value) return null
    const date = new Date(value)
    if (!Number.isFinite(date.getTime())) throw new Error('Choose valid announcement times.')
    return date.toISOString()
  }
  const starts_at = time(values.starts_at), ends_at = time(values.ends_at)
  if (starts_at && ends_at && starts_at >= ends_at) throw new Error('Announcement end must follow its start.')
  return { title, body, starts_at, ends_at, ...(row ? { version: row.version } : {}) }
}

export function assignmentPayload(camper, target, reason) {
  if (!target?.active) throw new Error('Select an active class first.')
  if (!reason.trim() || reason.trim().length > 500) throw new Error('Explain this assignment or transfer in 500 characters or fewer.')
  if (camper.assignment?.academic_class === target.id) throw new Error('This camper is already assigned to the selected class.')
  return { participant: camper.id, academic_class: target.id, reason: reason.trim(),
    ...(camper.assignment ? { assignment: camper.assignment.id, version: camper.assignment.version } : {}) }
}
