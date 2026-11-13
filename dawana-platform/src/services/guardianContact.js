import { ageOnDate } from './registrationPrivacy.js'

export const guardianReference = '2026-12-23'

export function requiresGuardianContact(participants = []) {
  return participants.some(person => {
    const age = ageOnDate(person.dob, guardianReference)
    return age !== null && age < 16
  })
}

export function validateGuardianContact(participants, contact) {
  if (requiresGuardianContact(participants) && !/^\d{7,15}$/.test(String(contact?.phone || '').replace(/\D/g, ''))) {
    throw new Error('Enter a valid parent or guardian phone number for participants below 16.')
  }
}
