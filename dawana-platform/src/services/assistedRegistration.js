export const assistedPreparationPath = '/assisted-registration/'
export function assistedBookingPayload(formData, requestId) {
  const count = formData.getAll('category_id').length
  const participants = Array.from({ length: count }, (_, index) => {
    const values = Object.fromEntries(Array.from(formData.keys(), key => [key,
      key.startsWith('payer_') ? formData.get(key) : formData.getAll(key)[index]]))
    return preparationPayload(values).registration.participants[0]
  })
  const payer = preparationPayload(Object.fromEntries(formData)).registration.primary_registrant
  return { request_id: requestId, registration: { primary_registrant: payer, participants } }
}
export const academicStatuses = ['Primary Student', 'Secondary Student', 'Tertiary Student', 'Graduate / Completed Tertiary Education', 'Not Currently in School']

export function preparationPayload(values) {
  const category = Number(values.category_id)
  if (!Number.isSafeInteger(category) || category < 1) throw new Error('Choose a registration category.')
  const participant = {}
  for (const name of ['full_name', 'address', 'phone', 'email', 'date_of_birth', 'sex', 'height_cm', 'weight_kg', 'academic_status', 'occupation', 'marital_status']) {
    participant[name] = String(values[name] || '').trim()
    if (!participant[name]) throw new Error('Complete every required camper field, including date of birth.')
  }
  const payer = { full_name: String(values.payer_name || '').trim(),
    email: String(values.payer_email || '').trim(), phone: String(values.payer_phone || '').trim() }
  if (!payer.full_name || (!payer.email && !payer.phone)) throw new Error('Provide the payer’s name and own recovery contact.')
  return { registration: { primary_registrant: payer, participants: [{ ...participant, category_id: category }] } }
}
