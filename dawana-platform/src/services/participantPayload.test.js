import test from 'node:test'
import assert from 'node:assert/strict'
import { participantOrders, participantExpiry } from './participantPayload.js'

test('unreadable dashboard payloads produce retryable errors instead of blank pages', () => {
  for (const value of [null, {}, { orders: {} }, { orders: [null] }, { orders: [{}] }]) {
    assert.throws(() => participantOrders(value), /Please retry/)
  }
  assert.deepEqual(participantOrders({ orders: [{ participants: [] }] }), [{ participants: [] }])
  assert.deepEqual(participantOrders({ orders: [] }), [])
})

test('only authenticated, unexpired session responses can initialize the portal', () => {
  const future = new Date(Date.now() + 60000).toISOString()
  assert.equal(participantExpiry({ authenticated: true, expires_at: future }), Date.parse(future))
  for (const data of [null, {}, { authenticated: false, expires_at: future },
    { authenticated: true, expires_at: 'invalid' }, { authenticated: true, expires_at: '2000-01-01' }]) {
    assert.throws(() => participantExpiry(data), /sign in again/)
  }
})
