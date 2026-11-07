export function productionApiBase(value = '/api/v1') {
  if (value !== '/api/v1') throw new Error('Production requires the same-origin /api/v1 gateway.')
  return value
}

// Draft contact, participant details, passwords and tokens stay in memory.
// After a refresh use verified booking recovery, never a new inferred order.
export function privateDraft(flow) {
  return {
    participants: [], idempotencyKey: flow.idempotencyKey,
    orderId: flow.orderId || null, paymentStatus: flow.paymentStatus,
    submissionUncertain: Boolean(flow.submissionUncertain), expiresAt: flow.expiresAt,
  }
}

export function registrationSubmission(flow, credentials, contactPayload, participantPayload, credentialsPayload) {
  if (!flow.participants.length) throw new Error('Use verified booking recovery after refreshing this page. Do not create or pay for another registration.')
  return { primary_registrant: contactPayload(flow.primaryRegistrant),
    participants: flow.participants.map(participantPayload), portal_account: credentialsPayload(credentials) }
}
