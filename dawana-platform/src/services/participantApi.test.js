import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { participantRequest, participantDeliveryOptions } from './participantApi.js'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { visibleOperationsNavigation } from './operationsNavigation.js'
import { eligibilityLabel, participantCardPath, staffCardPath } from './participantIdentity.js'

let deliveryServer, DeliveryStatus, IDPresentation

test('hung startup requests time out, clear shared work and permit a successful retry', async () => {
  const originalFetch = globalThis.fetch, originalTimeout = AbortSignal.timeout
  AbortSignal.timeout = () => originalTimeout(5)
  globalThis.fetch = (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true })
  })
  const keepAlive = setTimeout(() => {}, 1000)
  try {
    await assert.rejects(participantRequest('/auth/me/', undefined, { notifyExpiry: false }), /taking too long/)
    globalThis.fetch = async () => Response.json({ authenticated: true })
    assert.equal((await participantRequest('/auth/me/', undefined, { notifyExpiry: false })).authenticated, true)
  } finally {
    clearTimeout(keepAlive); globalThis.fetch = originalFetch; AbortSignal.timeout = originalTimeout
  }
})
before(async () => {
  deliveryServer = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  DeliveryStatus = (await deliveryServer.ssrLoadModule('/src/pages/ParticipantPortal.jsx')).ParticipantDeliveryStatus
  IDPresentation = (await deliveryServer.ssrLoadModule('/src/components/dic/DigitalIDPresentation.jsx')).default
})
after(async () => { await deliveryServer?.close() })

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

test('initial signed-out probe rejects access without showing an expired-session notice', async () => {
  const original = globalThis.fetch, previousWindow = globalThis.window
  const events = []
  globalThis.window = { dispatchEvent: event => events.push(event.type) }
  globalThis.fetch = async () => Response.json({ detail: 'Your participant session has expired. Please verify again.' }, { status: 403 })
  try {
    await assert.rejects(participantRequest('/auth/me/', undefined, { notifyExpiry: false }), error => error.status === 403)
    assert.deepEqual(events, [])
    await assert.rejects(participantRequest('/enrollments/'), error => error.status === 403)
    assert.deepEqual(events, ['participant-session-expired'])
    const page = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
    assert.match(page, /read\(ticket, '\/auth\/me\/', undefined, \{ notifyExpiry: false \}\)/)
  } finally { globalThis.fetch = original; globalThis.window = previousWindow }
})

test('delivery options preserve explicit unavailable channels and validate backend booleans', async () => {
  const original = globalThis.fetch
  const channels = [{ value: 'email', label: 'Email', available: false }, { value: 'sms', label: 'SMS', available: false }, { value: 'whatsapp', label: 'WhatsApp', available: false }]
  try {
    globalThis.fetch = async () => Response.json({ channels })
    assert.deepEqual(await participantDeliveryOptions({ refresh: true }), channels)
    for (const invalid of [[], null, [{ value: 'email', label: 'Email', available: 'false' }], [channels[0], channels[0]]]) {
      globalThis.fetch = async () => Response.json({ channels: invalid })
      await assert.rejects(participantDeliveryOptions({ refresh: true }), /Could not read secure code delivery availability/)
    }
    globalThis.fetch = async () => Response.json({ channels: [{ ...channels[0], available: true }] })
    assert.equal((await participantDeliveryOptions({ refresh: true }))[0].available, true)
  } finally { globalThis.fetch = original }
})

test('delivery check failure propagates as a failure, never an empty unavailable list', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => Response.json({ detail: 'Temporary outage' }, { status: 503 })
    await assert.rejects(participantDeliveryOptions({ refresh: true }), error => error.status === 503 && /Temporary outage/.test(error.message))
  } finally { globalThis.fetch = original }
})

test('delivery UI distinguishes loading, failed check, unavailable and configured channels', () => {
  const render = props => renderToStaticMarkup(createElement(DeliveryStatus, { channels: [], onRetry() {}, ...props }))
  assert.match(render({ phase: 'loading' }), /Checking secure code delivery availability/)
  assert.doesNotMatch(render({ phase: 'loading' }), /not currently available/)
  const failure = render({ phase: 'error', error: 'Temporary outage' })
  assert.match(failure, /Retry delivery check/)
  assert.doesNotMatch(failure, /not currently available/)
  assert.match(render({ phase: 'ready', channels: [{ available: false }] }), /Secure code delivery is not currently available/)
  assert.equal(render({ phase: 'ready', channels: [{ available: true }] }), '')
})

test('ID navigation requires its explicit permission and review messages do not imply arrival', () => {
  assert.equal(visibleOperationsNavigation({ permissions: { operations: true } }).some((i) => i.label === 'Participant IDs'), false)
  assert.equal(visibleOperationsNavigation({ permissions: { ids: true } }).some((i) => i.to === '/dic/operations/participant-ids'), true)
  assert.match(eligibilityLabel('source_review_required'), /staff review/)
  assert.match(eligibilityLabel('settlement_evidence_review_required'), /Payment evidence/)
})

test('print template exposes approved ID fields only and suppresses site controls', () => {
  const source = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
  assert.match(source, /return <DigitalIDPresentation card=\{card\} onClose=\{onClose\}/)
  const card = fs.readFileSync(new URL('../components/dic/DigitalIDPresentation.jsx', import.meta.url), 'utf8')
  for (const forbidden of ['date_of_birth', 'height_cm', 'weight_kg', 'address', 'phone', 'sessionid', 'access_token', 'qr_code', 'photo']) assert.equal(card.includes(forbidden), false)
  assert.match(card, /participant_number/)
  assert.match(card, /participantCardPath/)
  assert.doesNotMatch(card, /\/admin\//)
  const styles = fs.readFileSync(new URL('../pages/ParticipantPortal.css', import.meta.url), 'utf8')
  assert.match(styles, /@media print/)
  assert.match(styles, /break-inside: avoid/)
  assert.match(styles, /\.appearance-controls/)
})

test('portal ID links remain scoped read-only downloads for validated formats', () => {
  const id = '12345678-abcd-4321-abcd-123456789012'
  assert.equal(participantCardPath(id, 'portrait', true), `/api/v1/dic/participant/enrollments/${id}/card/?format=portrait&download=1`)
  assert.equal(participantCardPath(id), `/api/v1/dic/participant/enrollments/${id}/card/?format=pvc`)
  assert.equal(participantCardPath(id, 'a6', true), `/api/v1/dic/participant/enrollments/${id}/card/?format=a6&download=1`)
  assert.throws(() => participantCardPath('../other', 'pvc'))
  assert.throws(() => participantCardPath(id, 'bulk'))
  const source = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
  const open = source.slice(source.indexOf('const openID ='), source.indexOf('if (checking)'))
  assert.doesNotMatch(open, /registration_item_id|id_command/)
  assert.match(open, /participant\.issue\?\.status !== 'current'/)
})

test('staff card links use staff authorization while participant links retain booking scope', () => {
  const id = '12345678-abcd-4321-abcd-123456789012'
  for (const format of ['pvc', 'a6', 'portrait']) {
    assert.equal(staffCardPath(id, format, true), `/api/v1/dic/ids/cards/${id}/?format=${format}&download=1`)
    assert.match(participantCardPath(id, format), /\/dic\/participant\/enrollments\//)
  }
  assert.throws(() => staffCardPath('../other'))
  assert.throws(() => staffCardPath(id, 'bulk'))
})

test('issued ID presentation renders separate protected staff and participant downloads', () => {
  const card = { id: '12345678-abcd-4321-abcd-123456789012', name: 'Synthetic camper', participant_number: 'SYNTHETIC-ID' }
  const render = staff => renderToStaticMarkup(createElement(IDPresentation, { card, staff, onClose() {} }))
  const staff = render(true), participant = render(false)
  assert.match(staff, /href="(?:https:\/\/api\.dawanaislamicfoundation\.org)?\/api\/v1\/dic\/ids\/cards\//)
  assert.doesNotMatch(staff, /\/participant\/enrollments\//)
  assert.match(participant, /href="(?:https:\/\/api\.dawanaislamicfoundation\.org)?\/api\/v1\/dic\/participant\/enrollments\//)
  assert.doesNotMatch(participant, /\/ids\/cards\//)
  for (const html of [staff, participant]) {
    assert.match(html, /format=portrait&amp;download=1/)
    assert.doesNotMatch(html, /<iframe/)
  }
})
