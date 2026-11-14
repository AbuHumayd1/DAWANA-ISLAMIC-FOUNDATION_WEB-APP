import test from 'node:test'
import assert from 'node:assert/strict'
import { participantSessionAbsent, participantExpiry } from './participantPayload.js'
import { participantBackground } from '../components/dic/participantOptions.js'
import { returnedCamperKey } from './camperSelection.js'

test('ordinary signed-out and expired startup responses differ from malformed session data', () => {
  assert.equal(participantSessionAbsent({ authenticated: false }), true)
  assert.equal(participantSessionAbsent({ authenticated: true, expires_at: '2000-01-01' }), true)
  for (const data of [null, {}, { authenticated: true, expires_at: 'invalid' }]) {
    assert.equal(participantSessionAbsent(data), false)
    assert.throws(() => participantExpiry(data))
  }
  assert.equal(participantSessionAbsent({ authenticated: true, expires_at: new Date(Date.now() + 60000).toISOString() }), false)
})

test('checkout hides inapplicable background values without changing the underlying form data', () => {
  const original = { occupation: 'None', maritalStatus: 'None' }
  assert.equal(participantBackground(original), '')
  assert.deepEqual(original, { occupation: 'None', maritalStatus: 'None' })
  assert.equal(participantBackground({ occupation: 'Business', maritalStatus: 'None' }), 'Occupation: Business')
  assert.equal(participantBackground({ occupation: 'None', maritalStatus: 'Single' }), 'Marital status: Single')
})

test('ID return hint selects only an enrollment already in the authorized booking snapshot', () => {
  const orders = [{ reference: 'owned-booking', participants: [
    { id: 'first', registration_item_id: 1 }, { id: 'requested', registration_item_id: 2 },
  ] }]
  assert.equal(returnedCamperKey(orders, 'requested'), 'owned-booking:2')
  assert.equal(returnedCamperKey(orders, 'foreign'), null)
  assert.equal(returnedCamperKey([], 'requested'), null)
  assert.equal(returnedCamperKey([{ reference: 'owned', participants: [{ id: null, registration_item_id: 3 }] }], null), null)
})
