export function activityScoringPath(edition) {
  if (!/^[1-9]\d*$/.test(String(edition))) throw new Error('Choose a camp edition.')
  return `/scoring/activities/?edition=${edition}`
}

export function camperScoringPath(item, page = 1) {
  if (!/^[1-9]\d*$/.test(String(item)) || !Number.isInteger(page) || page < 1) throw new Error('Choose a camper and history page.')
  return `/scoring/?item=${item}&page=${page}`
}

export function campToday(now = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Africa/Lagos', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function activityPayload(values, rule, members, houses) {
  if (!rule || !values.date || !values.verified) throw new Error('Choose an activity and date, and verify completion.')
  const payload = { activity: rule.code, date: values.date, slot: values.slot || '', verified: true, note: values.note.trim() }
  if (rule.kind === 'individual') {
    if (!members.some(row => row.id === values.participant)) throw new Error('Choose an eligible camper.')
    payload.participant = values.participant
    if (rule.code === 'MIL05') payload.reading_target = values.reading_target.trim()
  } else {
    if (!houses.some(row => row.id === Number(values.house))) throw new Error('Choose a house.')
    payload.house = Number(values.house)
    const roster = members.filter(row => row.house === payload.house)
    const participation = ['participation', 'prayer_target'].includes(rule.mode)
    payload.exemptions = participation ? roster.filter(row => values.exemptions[row.id] !== undefined).map(row => ({ participant: row.id, reason: values.exemptions[row.id].trim() })) : []
    if (payload.exemptions.some(row => !row.reason)) throw new Error('Document each approved exemption.')
    payload.attendees = !participation || rule.mode === 'prayer_target' ? [] : roster.filter(row => values.attendees.includes(row.id) && values.exemptions[row.id] === undefined).map(row => row.id)
    if (['inspection', 'competition'].includes(rule.mode)) {
      payload.results = houses.filter(row => values.marks[row.id] !== undefined && values.marks[row.id] !== '').map(row => ({ house: row.id, marks: values.marks[row.id] }))
      if (!payload.results.length) throw new Error('Record the verified official assessment marks.')
    }
  }
  return payload
}

export function participationPreview(members, attendees, exemptions) {
  const eligible = new Set(members.map(row => row.id))
  const excluded = new Set(Object.keys(exemptions).filter(id => eligible.has(id)))
  const numerator = new Set(attendees.filter(id => eligible.has(id) && !excluded.has(id))).size
  const denominator = eligible.size - excluded.size
  return { numerator, denominator, percentage: denominator ? numerator * 100 / denominator : null }
}
