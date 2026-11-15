// These markers protect navigation only; they never grant server authority.
export function paymentProtectionRequired(flow) {
  return Boolean(flow?.paymentRequested || flow?.paymentReference || flow?.authorizationUrl
    || flow?.paymentStatus === 'paid'
    || (flow?.draftVersion !== 2 && (flow?.orderId || flow?.submissionUncertain)))
}

export function retainedRegistrationDraft(saved) {
  return paymentProtectionRequired(saved) ? saved : null
}

// Clear only this tab's draft, never account sessions, server orders or payments.
export function clearRegistrationDraft(storage) {
  try { (storage || globalThis.sessionStorage).removeItem('dawana.dic.registration.v1'); return true }
  catch { return false }
}
