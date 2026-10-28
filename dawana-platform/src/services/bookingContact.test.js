import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import fs from 'node:fs'
import { primaryRegistrantPayload, registrationCredentialsPayload } from './bookingContact.js'
let server, Fields
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Fields = (await server.ssrLoadModule('/src/components/dic/PrimaryRegistrantFields.jsx')).default
})
after(async () => { await server?.close() })
test('booking contact is explicit and normalized without borrowing a child identity', () => {
  assert.deepEqual(primaryRegistrantPayload({ fullName: ' Guardian ', email: ' Guardian@Example.test ', phone: '' }), { full_name: 'Guardian', email: 'guardian@example.test', phone: '' })
  for (const value of [undefined, {}, { fullName: 'Guardian' }, { email: 'guardian@example.test' }, { fullName: 'Guardian', email: 'invalid' }]) assert.throws(() => primaryRegistrantPayload(value))
})
test('registration shows explicit contact and keeps existing submitted contact locked', () => {
  const html = renderToStaticMarkup(createElement(Fields, { contact: {}, onChange() {}, locked: true }))
  assert.match(html, /fieldset disabled=""/); assert.match(html, /Booking email/); assert.match(html, /type="email"/)
  assert.match(html, /one-time email link/); assert.doesNotMatch(html, /type="password"/)
})
test('pre-payment password and confirmation are required but separate from persisted contact', () => {
  const password = 'River-Cedar!Sparrow-84'
  assert.deepEqual(registrationCredentialsPayload({ password, password_confirmation: password }), { password, password_confirmation: password })
  assert.throws(() => registrationCredentialsPayload({ password, password_confirmation: 'different' }))
  const html = renderToStaticMarkup(createElement(Fields, { contact: {}, onChange() {}, credentials: { password: '', password_confirmation: '' }, onCredentials() {} }))
  assert.equal((html.match(/type="password"/g) || []).length, 2)
})
test('post-payment activation submits password confirmation and requires verified email', () => {
  const source = fs.readFileSync(new URL('../components/dic/PortalAccountAccess.jsx', import.meta.url), 'utf8')
  assert.match(source, /password_confirmation: passwordConfirmation/)
  assert.match(source, /label="Confirm password"/)
  assert.doesNotMatch(source, /Continue with Google|Link Google to/)
})
test('registration persists only contact/draft data and submits explicit primary registrant', () => {
  const source = fs.readFileSync(new URL('../pages/DIC.jsx', import.meta.url), 'utf8')
  assert.match(source, /primary_registrant: primaryRegistrantPayload\(flow.primaryRegistrant\)/)
  const save = source.slice(source.indexOf('function saveFlow('), source.indexOf('function clearSavedFlow('))
  assert.doesNotMatch(save, /password|password_confirmation/)
  assert.match(source, /flow\.orderId \|\| busy \|\| flow\.submissionUncertain/)
})
