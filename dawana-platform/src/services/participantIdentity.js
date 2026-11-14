import { resolveMediaUrl } from './mediaUrl.js'

export function eligibilityLabel(code) {
  if (code === 'authorized_tutor') return 'Authorized complimentary tutor'
  if (code === 'tutor_authorization_required') return 'Tutor authorization unavailable or revoked'
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

export function participantCardPath(id, format = 'pvc', download = false) {
  return cardPath(id, format, download, false)
}

export function staffCardPath(id, format = 'pvc', download = false) {
  return cardPath(id, format, download, true)
}

function cardPath(id, format, download, staff) {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) || !['pvc', 'a6', 'portrait'].includes(format)) throw new Error('Invalid participant card selection')
  const base = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')
  const resource = staff ? `/dic/ids/cards/${id}/` : `/dic/participant/enrollments/${id}/card/`
  return resolveMediaUrl(`${base}${resource}?format=${format}${download ? '&download=1' : ''}${staff ? '&return_to=operations' : ''}`)
}
