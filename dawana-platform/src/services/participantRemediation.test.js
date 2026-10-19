import test from 'node:test'
import assert from 'node:assert/strict'
import { createLatestResource, createRequestScope, assertParticipantAccess } from './requestScope.js'
import { participantRequest } from './participantApi.js'
import { getOperationsData, getCsrfToken } from './operationsApi.js'

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('same staff search can repeat, recover from error, and return an empty result', async () => {
  const snapshots = []
  let requests = 0
  const resource = createLatestResource(async () => {
    if (++requests === 2) throw new Error('Temporary gateway error')
    return { results: [], page: 1 }
  }, (value) => snapshots.push(value))
  const search = { query: '', page: 1 }
  await resource.run(search)
  await resource.run(search)
  assert.equal(snapshots.at(-1).loading, false)
  assert.match(snapshots.at(-1).error, /gateway/)
  await resource.run(search)
  assert.equal(requests, 3)
  assert.deepEqual(snapshots.at(-1).data.results, [])
  assert.equal(snapshots.at(-1).error, '')
})

test('new staff search wins over delayed older results; explicit cancel and unmount ignore late results', async () => {
  const old = deferred(), latest = deferred()
  const snapshots = [], signals = []
  const resource = createLatestResource((parameters, signal) => {
    signals.push(signal)
    return parameters.query === 'old' ? old.promise : latest.promise
  }, (value) => snapshots.push(value))
  const first = resource.run({ query: 'old' })
  const second = resource.run({ query: 'new' })
  assert.equal(signals[0].aborted, true)
  latest.resolve({ results: ['current'] }); await second
  old.resolve({ results: ['stale'] }); await first
  assert.deepEqual(snapshots.at(-1).data.results, ['current'])
  const pending = deferred()
  const cancellable = createLatestResource(() => pending.promise, (value) => snapshots.push(value))
  const result = cancellable.run({ query: 'cancelled' })
  cancellable.cancel(true)
  pending.resolve({ results: ['must not appear'] }); await result
  assert.equal(snapshots.at(-1).cancelled, true)
  const count = snapshots.length
  cancellable.cancel() // effect cleanup must not publish to an unmounted component
  assert.equal(snapshots.length, count)
})

test('expiry/logout/unmount invalidate delayed participant enrollment, ID and verification commits', async () => {
  for (const operation of ['enrollments', 'card', 'verification']) {
    const scope = createRequestScope(), pending = deferred(), writes = []
    const ticket = scope.begin()
    const completion = pending.promise.then((data) => { scope.assert(ticket); writes.push(data) })
    scope.invalidate()
    assert.equal(ticket.signal.aborted, true)
    pending.resolve(operation)
    await assert.rejects(completion, { name: 'AbortError' })
    assert.deepEqual(writes, [])
    const next = scope.begin()
    assert.equal(scope.current(next), true)
    assert.equal(scope.current(ticket), false)
  }
})

test('elapsed participant deadline invalidates access before the expiry timer runs', () => {
  const scope = createRequestScope(), ticket = scope.begin()
  let cleared = false
  assert.throws(() => assertParticipantAccess(scope, ticket, Date.now()-1, () => {
    cleared = true; scope.invalidate()
  }), { name: 'AbortError' })
  assert.equal(cleared, true)
})

test('participant and staff clients preserve HTTP errors for HTML, empty and malformed responses', async () => {
  const original = globalThis.fetch
  try {
    for (const client of [participantRequest, getOperationsData]) {
      for (const [status, body] of [[502, '<html>private gateway detail</html>'], [503, ''], [200, '{broken'], [200, 'null']]) {
        globalThis.fetch = async () => new Response(body, { status })
        await assert.rejects(client('/enrollments/'), (error) => {
          assert.equal(error.status, status)
          assert.match(error.message, /retry/i)
          assert.equal(error.message.includes('private gateway'), false)
          return true
        })
      }
    }
  } finally { globalThis.fetch = original }
})

test('bad CSRF responses block mutations and clear initialization errors retain their status', async () => {
  const original = globalThis.fetch
  try {
    let calls = 0
    globalThis.fetch = async () => { calls++; return Response.json({ csrfToken: '' }) }
    await assert.rejects(participantRequest('/auth/verify/', { code: '123456' }), /secure access/)
    assert.equal(calls, 1)
    await assert.rejects(getCsrfToken(), /secure access/)
    globalThis.fetch = async () => new Response('<html>unavailable</html>', { status: 502 })
    await assert.rejects(participantRequest('/auth/logout/', {}), (error) => error.status === 502)
  } finally { globalThis.fetch = original }
})

test('aborted stale participant requests never publish session-expired events', async () => {
  const originalFetch = globalThis.fetch, originalWindow = globalThis.window
  const controller = new AbortController(), pending = deferred(), events = []
  globalThis.window = { dispatchEvent: (event) => events.push(event.type) }
  globalThis.fetch = () => pending.promise // deliberately ignores AbortSignal
  try {
    const result = participantRequest('/auth/me/', undefined, { signal: controller.signal })
    controller.abort()
    pending.resolve(Response.json({ detail: 'Your participant session has expired. Please verify again.' }, { status: 403 }))
    await assert.rejects(result, { name: 'AbortError' })
    assert.deepEqual(events, [])
  } finally { globalThis.fetch = originalFetch; globalThis.window = originalWindow }
})


test('cancelling during CSRF initialization prevents a stale participant mutation', async () => {
  const original = globalThis.fetch, csrf = deferred(), controller = new AbortController()
  let requests = 0
  globalThis.fetch = () => { requests++; return csrf.promise }
  try {
    const result = participantRequest('/enrollments/', { registration_item_id: 1 }, { signal: controller.signal })
    controller.abort()
    csrf.resolve(Response.json({ csrfToken: 'valid-but-stale' }))
    await assert.rejects(result, { name: 'AbortError' })
    assert.equal(requests, 1)
  } finally { globalThis.fetch = original }
})
