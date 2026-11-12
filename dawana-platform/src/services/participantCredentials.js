const reserved = new Set(['admin', 'administrator', 'staff', 'supervisor', 'superuser', 'root', 'support', 'system', 'dic', 'dif', 'dawana', 'api', 'tutor', 'operations'])

export function normalizeParticipantUsername(value) {
  const username = String(value || '').trim().toLowerCase()
  if (!/^[a-z0-9][a-z0-9_. -]{0,39}$/.test(username) || username.includes('  ')
    || reserved.has(username) || username.startsWith('dic_')
    || /^(admin(?:istrator)?|staff|dawana|operations)[ ._-]/.test(username)) {
    throw new Error('Use up to 40 letters, numbers, spaces, dots, hyphens or underscores. Start with a letter or number; official names are reserved.')
  }
  return username
}

export function participantPassword(value) {
  if (typeof value !== 'string' || !value.length || value.length > 128) throw new Error('Enter a nonempty password of at most 128 characters.')
  return value
}
