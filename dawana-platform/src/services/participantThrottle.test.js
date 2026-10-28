import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import fs from 'node:fs'
let counter = 0, server, Status
const fresh = () => import(`./participantApi.js?throttle-test=${++counter}`)
const channels = [{ value: 'email', label: 'Email', available: true }]
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Status = (await server.ssrLoadModule('/src/pages/ParticipantPortal.jsx')).ParticipantAuthStatus
})
after(async () => { await server?.close() })

test('simultaneous availability subscribers share a single request and remount uses cached public options', async () => {
  const api = await fresh(), original = globalThis.fetch
  let resolve, count = 0
  globalThis.fetch = () => { count++; return new Promise(done => { resolve = done }) }
  try {
    const first = api.participantDeliveryOptions(), second = api.participantDeliveryOptions()
    assert.equal(count, 1)
    resolve(Response.json({ channels }))
    assert.deepEqual(await first, channels); assert.deepEqual(await second, channels)
    for (let render = 0; render < 20; render++) assert.deepEqual(await api.participantDeliveryOptions(), channels)
    assert.equal(count, 1)
    globalThis.fetch = async () => { count++; return Response.json({ channels }) }
    await api.participantDeliveryOptions({ refresh: true })
    assert.equal(count, 2)
  } finally { globalThis.fetch = original }
})

test('StrictMode cleanup aborts only its subscriber, leaving one request for the next mount', async () => {
  const api = await fresh(), original = globalThis.fetch
  let resolve, count = 0
  globalThis.fetch = () => { count++; return new Promise(done => { resolve = done }) }
  try {
    const abandoned = new AbortController()
    const first = api.participantDeliveryOptions({ signal: abandoned.signal })
    abandoned.abort()
    const rejected = assert.rejects(first, { name: 'AbortError' })
    const second = api.participantDeliveryOptions()
    resolve(Response.json({ channels }))
    await rejected; assert.deepEqual(await second, channels)
    assert.equal(count, 1)
  } finally { globalThis.fetch = original }
})

test('initial session probe is coalesced but authenticated session results are never cached', async () => {
  const api = await fresh(), original = globalThis.fetch
  let resolve, count = 0
  globalThis.fetch = () => { count++; return new Promise(done => { resolve = done }) }
  try {
    const first = api.participantRequest('/auth/me/', undefined, { notifyExpiry: false })
    const second = api.participantRequest('/auth/me/', undefined, { notifyExpiry: false })
    assert.equal(count, 1)
    resolve(Response.json({ authenticated: true, expires_at: '2026-12-23T12:30:00Z' }))
    await first; await second
    globalThis.fetch = async () => { count++; return Response.json({ authenticated: true }) }
    await api.participantRequest('/auth/me/', undefined, { notifyExpiry: false })
    assert.equal(count, 2)
  } finally { globalThis.fetch = original }
})

test('429 Retry-After blocks shared-scope retries until deadline and permits successful recovery', async () => {
  const api = await fresh(), original = globalThis.fetch, clock = Date.now
  let now = 100000, count = 0
  Date.now = () => now
  globalThis.fetch = async () => { count++; return Response.json({ detail: 'Request was throttled.' }, { status: 429, headers: { 'Retry-After': '64' } }) }
  try {
    await assert.rejects(api.participantDeliveryOptions(), error => error.status === 429 && error.retryAt === 164000)
    for (const path of ['/auth/options/', '/auth/me/', '/enrollments/']) await assert.rejects(api.participantRequest(path), error => error.status === 429 && error.retryAt === 164000)
    assert.equal(count, 1)
    now = 163999
    await assert.rejects(api.participantDeliveryOptions({ refresh: true }), error => error.status === 429)
    now = 164000
    globalThis.fetch = async () => { count++; return Response.json({ channels }) }
    assert.deepEqual(await api.participantDeliveryOptions(), channels)
    assert.equal(count, 2)
  } finally { globalThis.fetch = original; Date.now = clock }
})

test('429 supports HTTP date headers and server message fallback', async () => {
  const original = globalThis.fetch, clock = Date.now
  Date.now = () => Date.parse('2026-10-25T12:00:00Z')
  try {
    for (const headers of [{ 'Retry-After': 'Sun, 25 Oct 2026 12:01:04 GMT' }, {}]) {
      const api = await fresh()
      globalThis.fetch = async () => Response.json({ detail: 'Request was throttled. Expected available in 64 seconds.' }, { status: 429, headers })
      await assert.rejects(api.participantDeliveryOptions(), error => error.retryAt === Date.now() + 64000)
    }
  } finally { globalThis.fetch = original; Date.now = clock }
})

test('one authentication alert covers simultaneous session and delivery throttling, with countdown and retry', () => {
  const props = { retryUntil: 164000, now: 100000, error: 'Request was throttled.', phase: 'error', channels: [], deliveryError: 'Request was throttled.', onRetry() {} }
  const render = extra => renderToStaticMarkup(createElement(Status, { ...props, ...extra }))
  const waiting = render({})
  assert.equal((waiting.match(/role="alert"/g) || []).length, 1)
  assert.match(waiting, /64 seconds/); assert.match(waiting, /disabled=""/)
  assert.doesNotMatch(waiting, /Could not check|not currently available/)
  const ready = render({ now: 164000 })
  assert.match(ready, /Retry secure access/); assert.doesNotMatch(ready, /disabled=""/)
  const recovered = render({ retryUntil: 0, error: '', phase: 'ready', channels })
  assert.equal(recovered, '')
})

test('delivery options load only for explicit recovery while submissions retain duplicate guards', () => {
  const page = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
  assert.match(page, /\}, \[deliveryAttempt, loginOpen, challenge\]\)/)
  assert.match(page, /if \(!loginOpen && !challenge\) return undefined/)
  assert.equal((page.match(/<ParticipantAuthStatus /g) || []).length, 1)
  assert.doesNotMatch(page, /<ParticipantDeliveryStatus phase=\{deliveryPhase\}/)
  assert.match(page, /actionPending.current \|\| Date.now\(\) < retryUntil/)
  assert.match(page, /challenge && Date.now\(\) < resendAt/)
})
