export function bookingReference(value) {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value) ? value : ''
}

export function sessionPersistenceLabel(seconds) {
  const minutes = Math.floor(Number(seconds) / 60)
  if (!Number.isFinite(minutes) || minutes < 1 || minutes > 480) return '30 minutes'
  if (minutes >= 60) return `${minutes / 60} ${minutes === 60 ? 'hour' : 'hours'}`
  return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`
}

export async function continueToPortal(reference, request) {
  const order = bookingReference(reference)
  if (!order) throw new Error('Recover your booking reference before continuing.')
  try {
    const result = await request('/auth/continue/', { order_reference: order }, { notifyExpiry: false })
    if (result?.order_reference !== order || (result.authenticated !== true && result.requires_verification !== true)) {
      throw new Error('Could not validate secure portal continuation. Use booking verification.')
    }
    return { bookingReference: order }
  } catch (error) {
    // Missing return/session authority never authenticates. Recovery still requires OTP.
    if ([401, 403, 404].includes(error.status)) return { bookingReference: order }
    throw error
  }
}

export const portalIntegrationSlots = [
  { id: 'today', title: "Today's Activities", phase: 4 },
  { id: 'timetable', title: 'Full Camp Timetable', phase: 4 },
  { id: 'duties', title: 'House Duties', phase: 4, competitiveCamperOnly: true },
  { id: 'food', title: 'Food Timetable', phase: 4 },
  { id: 'id', title: 'Digital ID and QR Code' },
  { id: 'daily-feedback', title: 'Daily Feedback', phase: 5, channel:'daily' },
  { id: 'evaluation', title: 'Final Camp Evaluation', phase: 5, channel:'final' },
  { id: 'complaint', title: 'Submit a Complaint', phase: 5, channel:'welfare' },
  { id: 'complaint-history', title: 'My Complaints / Complaint Status', phase: 5, channel:'history' },
]
