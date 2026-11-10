export const portalDestinations = [
  ['home', 'Home'], ['day', 'My Day'], ['arena', 'Arena'], ['explore', 'Explore'], ['me', 'Me'],
]

export function portalView(value) {
  const aliases = { timetables: 'day', houses: 'arena', points: 'arena', camp: 'explore', profile: 'me' }
  return Object.hasOwn(aliases, value) ? aliases[value] : (['home', 'day', 'arena', 'explore', 'me', 'digital-id', 'feedback', 'announcements'].includes(value) ? value : 'home')
}

export function activeDestination(view) {
  return ['feedback', 'announcements'].includes(view) ? 'explore' : view === 'digital-id' ? 'me' : view
}

export function todayProgramme(data) {
  return data?.state === 'published' && data.date === data.today ? data.entries : []
}

export function campDayLabel(data) {
  if (!data?.today || !data.dates?.length) return 'Camp day pending'
  const day = data.dates.findIndex(row => row.date === data.today)
  if (day >= 0) return `Camp day ${day + 1}`
  return data.today < data.dates[0].date ? 'Camp begins soon' : 'Camp has concluded'
}

export function digitalIDState(participant) {
  if (!participant.eligibility?.eligible) return {
    available: false, title: 'Your ID needs a staff review',
    detail: 'Registration eligibility must be confirmed before an active Digital ID can be opened. Contact authorized DIC staff.',
  }
  if (participant.id && participant.issue?.status === 'current') return {
    available: true, title: 'Your Digital ID is ready',
    detail: 'Open your authorized card, QR code and available download formats.',
  }
  const preparing = ['pending', 'processing', 'held', 'failed'].includes(participant.fulfillment?.state)
  return { available: false, title: 'Your Digital ID is being prepared',
    detail: participant.issue?.status === 'revoked'
      ? 'The previous ID is no longer active. Ask authorized DIC staff to review issuance.'
      : (preparing && participant.fulfillment?.message) || 'Your registration is eligible. Your Digital ID will appear here when issuance is complete. If it remains pending, ask the DIC team to check its status.',
  }
}
