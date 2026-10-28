export function primaryRegistrantPayload(contact) {
  const full_name = String(contact?.fullName || '').trim()
  const email = String(contact?.email || '').trim().toLowerCase()
  const phone = String(contact?.phone || '').trim()
  if (!full_name || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('Enter the primary camper or guardian name and a valid booking email before creating the order.')
  return { full_name, email, phone }
}

export function registrationCredentialsPayload(credentials) {
  const password = credentials?.password || ''
  const confirmation = credentials?.password_confirmation || ''
  if (password.length < 12 || password.length > 128) throw new Error('Use a password between 12 and 128 characters.')
  if (password !== confirmation) throw new Error('Passwords must match.')
  return { password, password_confirmation: confirmation }
}
