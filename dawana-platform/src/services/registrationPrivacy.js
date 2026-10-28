export function ageOnDate(birth, reference) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(birth || '') || !reference || birth > reference) return null
  const [year, month, day] = birth.split('-').map(Number)
  const parsed = new Date(`${birth}T12:00:00Z`)
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== birth) return null
  const [refYear, refMonth, refDay] = reference.split('-').map(Number)
  return refYear - year - (refMonth < month || (refMonth === month && refDay < day) ? 1 : 0)
}

export function privacyPayload(participant, today) {
  const choice = participant.ageChoice || (participant.dob ? 'exact' : '')
  if (!['minor', 'adult_dob', 'adult_private', 'exact'].includes(choice)) throw new Error('Choose minor or adult registration.')
  const birth = choice === 'adult_private' ? null : participant.dob
  if (birth !== null) {
    const age = ageOnDate(birth, today)
    if (age === null) throw new Error('Provide a valid date of birth that is not in the future.')
    if (choice === 'minor' && age >= 18) throw new Error('Choose adult registration for campers aged 18 or older.')
    if (choice === 'adult_dob' && age < 18) throw new Error('Adult registration requires age 18 or older.')
  }
  const measurement = value => {
    if (value === null || value === undefined || String(value).trim() === '') return null
    const text = String(value).trim()
    if (!/^\d{1,8}(\.\d{1,2})?$/.test(text) || Number(text) <= 0) throw new Error('Supplied measurements must be positive numbers with at most two decimal places.')
    return text
  }
  return { age_declaration: choice.startsWith('adult') ? 'adult' : choice,
    date_of_birth: birth, height_cm: measurement(participant.height), weight_kg: measurement(participant.weight) }
}

export function privacySummary(participant) {
  return participant.ageChoice === 'adult_private' ? 'Adult (18+) — exact DOB not disclosed'
    : participant.dob ? `Date of birth: ${participant.dob}` : 'Date of birth not disclosed'
}
