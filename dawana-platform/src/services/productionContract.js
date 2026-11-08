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
  const guardians = (flow.primaryRegistrant?.guardianRelationships || [])
    .filter(row => flow.participants.some(person => person.id === row.childId)).map(row => {
    const child_index = flow.participants.findIndex(person => person.id === row.childId)
    const guardian_index = flow.participants.findIndex(person => person.id === row.guardianId)
    if (child_index < 0 || guardian_index < 0 || child_index === guardian_index || row.confirmed !== true) {
      throw new Error('Review and confirm the selected guardian for each dependent child.')
    }
    return { child_index, guardian_index, confirmed: true }
  })
  return { primary_registrant: contactPayload(flow.primaryRegistrant),
    participants: flow.participants.map(participantPayload), portal_account: credentialsPayload(credentials),
    ...(guardians.length ? { guardian_relationships: guardians } : {}) }
}
