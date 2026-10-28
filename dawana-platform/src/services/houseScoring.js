export function scoringPath(edition = '', page = 1) {
  if (edition && !/^[1-9]\d*$/.test(String(edition))) throw new Error('Choose a valid camp edition.')
  if (!Number.isInteger(page) || page < 1) throw new Error('Choose a valid history page.')
  const query = new URLSearchParams({ page: String(page) })
  if (edition) query.set('edition', edition)
  return `/scoring/?${query}`
}

export function scorePayload(values) {
  if (!/^[1-9]\d*$/.test(String(values.house))) throw new Error('Choose a house.')
  if (!['award', 'deduction'].includes(values.entry_type)) throw new Error('Choose Award or Deduction.')
  if (!/^[1-9]\d*$/.test(String(values.points)) || Number(values.points) > 2147483647) throw new Error('Points must be a positive whole number, up to 2147483647.')
  const activity = values.activity.trim(), note = (values.note || '').trim()
  if (!activity || activity.length > 200) throw new Error('Enter an activity or reason, up to 200 characters.')
  if (note.length > 1000) throw new Error('Keep the note within 1000 characters.')
  return { house: Number(values.house), entry_type: values.entry_type, points: Number(values.points), activity, note }
}

// Retain a submission reference after an uncertain network result. A successful
// save resets it; changed details receive a new reference.
export function submissionReference(previous, payload, makeId = () => crypto.randomUUID()) {
  const signature = JSON.stringify(payload)
  return previous?.signature === signature ? previous : { signature, id: makeId() }
}
