export function eligibilityLabel(code) {
  return {
    verified_paid: 'Registration payment verified',
    registration_not_verified_paid: 'The registration is not currently confirmed and verified paid.',
    settlement_evidence_review_required: 'Payment evidence needs authorized staff review.',
    reconciliation_review_required: 'Payment reconciliation needs authorized staff review.',
    source_review_required: 'Multiple registration sources need authorized staff review.',
    restricted_review_required: 'An ID restriction needs authorized staff review.',
    invalid_source: 'The registration source needs authorized staff review.',
  }[code] || 'Please contact authorized DIC staff for review.'
}
