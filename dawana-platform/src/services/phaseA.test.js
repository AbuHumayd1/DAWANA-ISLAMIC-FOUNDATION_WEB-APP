import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { normalizeParticipantUsername, participantPassword } from './participantCredentials.js'
import { registrationCredentialsPayload } from './bookingContact.js'
import { registrationExpired, resumablePaymentReference } from './orderLifecycle.js'

test('expiry UI uses activated deadlines and preserves protected paid/tutor and original attempts', () => {
  const time = Date.parse('2026-11-13T10:00:00Z')
  const lifecycle = { enforced: true, expired: false, expires_at: '2026-11-13T10:00:00Z' }
  assert.equal(registrationExpired(lifecycle, time - 1), false)
  assert.equal(registrationExpired(lifecycle, time), true)
  assert.equal(registrationExpired({ ...lifecycle, enforced: false }, time), false)
  assert.equal(registrationExpired(undefined, time), false)
  assert.equal(resumablePaymentReference({ payment_attempts: [{ reference: 'original-ref', status: 'pending' }] }), 'original-ref')
})

test('participant credentials accept all nonempty short/common/symbol/space secrets without trimming', () => {
  for (const password of ['x', 'password', '123', '!', ' ', ' two words ']) {
    assert.equal(participantPassword(password), password)
    assert.equal(registrationCredentialsPayload({ username: 'Parent Name', mode: 'create', password, password_confirmation: password }).password, password)
  }
  for (const password of ['', undefined, 'x'.repeat(129)]) assert.throws(() => participantPassword(password))
})
test('simple usernames normalize consistently and preserve reserved-name boundaries', () => {
  assert.equal(normalizeParticipantUsername(' Parent Name '), 'parent name')
  assert.equal(normalizeParticipantUsername('x'), 'x')
  for (const name of ['ADMIN', 'staff login', 'dawana support', 'dic_private', '/bad', 'two  spaces', 'x'.repeat(41)]) assert.throws(() => normalizeParticipantUsername(name))
})
test('existing account mode authenticates without demanding a new-password confirmation', () => {
  assert.deepEqual(registrationCredentialsPayload({ username: 'Parent Name', mode: 'existing', password: 'x' }), { username: 'parent name', mode: 'existing', password: 'x' })
  assert.throws(() => registrationCredentialsPayload({ username: 'new name', mode: 'create', password: 'x' }))
})
test('registration offers separate create/reuse modes with appropriate password-manager hints', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: Fields } = await vite.ssrLoadModule('/src/components/dic/PrimaryRegistrantFields.jsx')
    const render = mode => renderToStaticMarkup(createElement(Fields, { contact: {}, onChange() {}, onCredentials() {}, credentials: { mode, username: '', password: '', password_confirmation: '' } }))
    const create = render('create'), existing = render('existing')
    assert.match(create, /Create a new participant account/)
    assert.match(create, /Use an existing participant account/)
    assert.equal((create.match(/type="password"/g) || []).length, 2)
    assert.equal((existing.match(/type="password"/g) || []).length, 1)
    assert.match(existing, /autoComplete="current-password"/)
    assert.doesNotMatch(create, /minLength=/)
  } finally { await vite.close() }
})
