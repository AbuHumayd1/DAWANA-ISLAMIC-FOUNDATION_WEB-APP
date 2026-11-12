import { normalizeParticipantUsername, participantPassword } from './participantCredentials.js'

export function primaryRegistrantPayload(contact) {
  const full_name = String(contact?.fullName || '').trim()
  const email = String(contact?.email || '').trim().toLowerCase()
  const phone = String(contact?.phone || '').trim()
  if (!full_name || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('Enter the primary camper or guardian name and a valid booking email before creating the order.')
  return { full_name, email, phone }
}

export function registrationCredentialsPayload(credentials) {
  const username = normalizeParticipantUsername(credentials?.username)
  const password = participantPassword(credentials?.password)
  const confirmation = credentials?.password_confirmation || ''
  if (credentials?.mode !== 'existing' && password !== confirmation) throw new Error('Passwords must match.')
  return { username, password, ...(credentials?.mode ? { mode: credentials.mode } : {}),
    ...(credentials?.mode === 'existing' ? {} : { password_confirmation: confirmation }) }
}
