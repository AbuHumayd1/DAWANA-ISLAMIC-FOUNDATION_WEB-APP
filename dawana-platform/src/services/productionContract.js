export function productionApiBase(value) {
  if (value === '/api/v1') return value // Local/archived same-origin builds.
  try {
    const url = new URL(value)
    if (url.protocol === 'https:' && !url.username && !url.password && !url.search
      && !url.hash && url.pathname === '/api/v1' && ['', '443'].includes(url.port)
      && value === `${url.origin}/api/v1`) return value
  } catch { /* Report configuration without printing its supplied value. */ }
  throw new Error('Set VITE_API_BASE_URL to the exact HTTPS backend origin followed by /api/v1.')
}

export function backendUrl(path, apiBase = import.meta.env?.VITE_API_BASE_URL || '/api/v1') {
  const base = productionApiBase(apiBase)
  return (base === '/api/v1' ? '' : new URL(base).origin) + path
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
