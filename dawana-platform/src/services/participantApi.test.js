import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { participantRequest } from './participantApi.js'
import { visibleOperationsNavigation } from './operationsNavigation.js'
import { eligibilityLabel } from './participantIdentity.js'

test('participant mutations use isolated cookie path, fresh CSRF and no bearer storage', async () => {
  const original = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return Response.json(url.endsWith('/csrf/') ? { csrfToken: 'masked-test-csrf' } : { authenticated: true })
  }
  try {
    await participantRequest('/auth/verify/', { challenge_id: 'test-challenge', code: '123456' })
    assert.equal(calls.length, 2)
    assert.ok(calls.every((c) => c.url.startsWith('/api/v1/dic/participant/')))
    assert.equal(calls[1].options.credentials, 'include')
    assert.equal(calls[1].options.headers.get('X-CSRFToken'), 'masked-test-csrf')
    assert.equal(calls[1].options.headers.has('Authorization'), false)
    assert.equal(calls[1].options.cache, 'no-store')
    assert.equal(calls[1].url.includes('123456'), false)
  } finally { globalThis.fetch = original }
})

test('expired participant access notifies only the participant UI', async () => {
  const original = globalThis.fetch
  const previousWindow = globalThis.window
  const events = []
  globalThis.window = { dispatchEvent: (event) => events.push(event.type) }
  globalThis.fetch = async () => Response.json({ detail: 'Your participant session has expired. Please verify again.' }, { status: 403 })
  try {
    await assert.rejects(participantRequest('/auth/me/'), (error) => error.status === 403)
    assert.deepEqual(events, ['participant-session-expired'])
  } finally { globalThis.fetch = original; globalThis.window = previousWindow }
})

test('ID navigation requires its explicit permission and review messages do not imply arrival', () => {
  assert.equal(visibleOperationsNavigation({ permissions: { operations: true } }).some((i) => i.label === 'Participant IDs'), false)
  assert.equal(visibleOperationsNavigation({ permissions: { ids: true } }).some((i) => i.to === '/dic/operations/participant-ids'), true)
  assert.match(eligibilityLabel('source_review_required'), /staff review/)
  assert.match(eligibilityLabel('settlement_evidence_review_required'), /Payment evidence/)
})

test('print template exposes approved ID fields only and suppresses site controls', () => {
  const source = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
  const card = source.slice(source.indexOf('export function ParticipantIDCard'), source.indexOf('export default'))
  for (const forbidden of ['date_of_birth', 'height_cm', 'weight_kg', 'address', 'phone', 'sessionid', 'access_token', 'qr_code', 'photo']) assert.equal(card.includes(forbidden), false)
  assert.match(card, /participant_number/)
  assert.match(card, /window.print/)
  const styles = fs.readFileSync(new URL('../pages/ParticipantPortal.css', import.meta.url), 'utf8')
  assert.match(styles, /@media print/)
  assert.match(styles, /break-inside: avoid/)
  assert.match(styles, /\.appearance-controls/)
})
