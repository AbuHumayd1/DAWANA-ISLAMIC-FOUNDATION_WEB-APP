export function registrationExpired(lifecycle, now = Date.now()) {
  return Boolean(lifecycle?.expired || (lifecycle?.enforced && Date.parse(lifecycle.expires_at) <= now))
}

export function resumablePaymentReference(order) {
  return order?.payment_attempts?.find(row => ['pending', 'initializing', 'init_unknown', 'verify_pending', 'reconcile', 'amount_mismatch'].includes(row.status))?.reference || null
}
