import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import { bookingReference, continueToPortal, portalIntegrationSlots, sessionPersistenceLabel } from './portalPhase3.js'

const reference = '12345678-1234-4123-8123-123456789abc'
let server, components
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  components = await server.ssrLoadModule('/src/components/dic/PortalPhase3.jsx')
})
after(async () => { await server?.close() })
const render = (name, props) => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(components[name], props)))

test('only a UUID booking reference is a recovery hint; URL flags are not authority', () => {
  assert.equal(bookingReference(reference), reference)
  for (const value of ['?paid=true', 'https://evil.invalid', null, { toString: () => reference }, 'token=secret']) assert.equal(bookingReference(value), '')
})
test('personal-device persistence is displayed with a bounded, human-readable duration', () => {
  assert.equal(sessionPersistenceLabel(28800), '8 hours')
  assert.equal(sessionPersistenceLabel(1800), '30 minutes')
  assert.equal(sessionPersistenceLabel(3600), '1 hour')
  assert.equal(sessionPersistenceLabel(Infinity), '30 minutes')
})
test('existing server-verified continuation carries only the exact booking hint', async () => {
  const result = await continueToPortal(reference, async (path, body, options) => {
    assert.equal(path, '/auth/continue/'); assert.deepEqual(body, { order_reference: reference }); assert.equal(options.notifyExpiry, false)
    return { authenticated: true, order_reference: reference, token: 'never-carry', redirect: 'https://evil.invalid' }
  })
  assert.deepEqual(result, { bookingReference: reference })
})
test('payment return without identity verification explicitly goes to OTP', async () => {
  assert.deepEqual(await continueToPortal(reference, async () => ({ authenticated: false, requires_verification: true, order_reference: reference })), { bookingReference: reference })
})
test('missing, expired or revoked session falls back to verification without authenticated state', async () => {
  for (const status of [401, 403, 404]) {
    const result = await continueToPortal(reference, async () => { throw Object.assign(new Error('Unavailable'), { status }) })
    assert.deepEqual(result, { bookingReference: reference }); assert.equal(result.authenticated, undefined)
  }
})
test('cross-booking or fabricated continuation responses are rejected', async () => {
  for (const result of [null, {}, { authenticated: 'true', order_reference: reference }, { authenticated: true, order_reference: 'foreign' }]) {
    await assert.rejects(continueToPortal(reference, async () => result))
  }
})
test('rate limits and network failures never masquerade as successful continuation', async () => {
  for (const status of [0, 429, 500]) await assert.rejects(continueToPortal(reference, async () => { throw Object.assign(new Error('Retry'), { status }) }))
})
test('deferred Google is hidden while verification-code access remains available', () => {
  const html = render('PortalLoginChoices', { open: false, onVerify() {} })
  assert.doesNotMatch(html, /Continue with Google/)
  assert.match(html, /Use a verification code/)
  assert.doesNotMatch(html, /accounts\.google|client_secret|password/i)
})
test('class card separates registration category from teaching class without fabricating assignment', () => {
  const html = render('ClassAssignmentCard', { participant: { category: 'Age category', class_assignment: { name: 'Unapproved class' } } })
  assert.match(html, /My Class/); assert.match(html, /Not yet assigned/)
  assert.match(html, /Your class will appear here/); assert.doesNotMatch(html, /Unapproved class|Age category/)
})

test('approved academic assignment is shown and safely escaped', () => {
  const html = render('ClassAssignmentCard', { participant: { category: 'Age category', class_assignment: { status: 'assigned', name: '<b>Approved class</b>', message: 'Assigned by officer' } } })
  assert.match(html, /&lt;b&gt;Approved class&lt;\/b&gt;/)
  assert.doesNotMatch(html, /Not yet assigned/)
  assert.match(html, /My Class/)
  assert.doesNotMatch(html, /Assigned by officer|Registration category:/)
})
test('tutors retain role separation and never receive class or house-duty assignments', () => {
  const participant = { registration_basis: 'tutor', eligibility: { eligible: true }, issue: null }
  const html = render('ClassAssignmentCard', { participant }) + render('PortalIntegrations', { participant, onOpenID() {} })
  assert.match(html, /does not apply/); assert.doesNotMatch(html, /House Duties|House assignment|My Points|Not yet assigned/)
})
test('later module locations are explicit unavailable states, with no new operational endpoints', () => {
  const html = render('PortalIntegrations', { participant: {}, onOpenID() {} })
  assert.equal(portalIntegrationSlots.length, 9)
  assert.match(html, /Today&#x27;s Activities/); assert.match(html, /Full Camp Timetable/)
  assert.match(html, /Coming later/); assert.match(html, /No information is available here yet/)
  assert.match(html, /channel=daily/); assert.doesNotMatch(html, /0 points|0 meals|0 tasks/)
})
test('existing ID issuance and eligibility gates stay on dashboard integration points', () => {
  const denied = render('PortalIntegrations', { participant: { id: 'camper', eligibility: { eligible: false }, issue: { status: 'current' } }, onOpenID() {} })
  assert.match(denied, /disabled=""[^>]*>Open digital ID/)
  const allowed = render('PortalIntegrations', { participant: { id: 'camper', eligibility: { eligible: true }, issue: { status: 'current' } }, onOpenID() {} })
  assert.doesNotMatch(allowed, /disabled=""[^>]*>Open digital ID/)
})
test('camper switching uses current server booking snapshot and clears old ID before selection', () => {
  const source = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
  assert.match(source, /access\.invalidate\(\); setCard\(null\); setSelection\(value\)/)
  assert.match(source, /\/auth\/me\//); assert.match(source, /remember_device: rememberDevice/)
})
test('decorations retain semantic hiding, focus states and normal document scrolling', () => {
  assert.match(render('PortalScenery', {}), /aria-hidden="true"/)
  const css = fs.readFileSync(new URL('../components/dic/PortalPhase3.css', import.meta.url), 'utf8')
  assert.match(css, /focus-visible/)
  assert.doesNotMatch(css, /overflow(?:-y)?:\s*(auto|scroll)|height:\s*100(?:d|s)?vh|position:\s*fixed/)
})
