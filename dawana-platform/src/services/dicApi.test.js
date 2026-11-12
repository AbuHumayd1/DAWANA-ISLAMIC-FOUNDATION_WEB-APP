import test from 'node:test'
import assert from 'node:assert/strict'
import { createRegistrationOrder, initializePayment, verifyPayment, getRegistrationOrder } from './dicApi.js'

test('nested order validation errors identify the account and participant instead of generic HTTP 400', async () => {
  const original = globalThis.fetch
  const bodies = [
    { portal_account: { non_field_errors: ['This password is entirely numeric.'] } },
    { participants: [{}, { email: ['Enter a valid email address.'], occupation: ['"private-input" is not a valid choice.'] }] },
    { participants: { '1': { email: ['Enter a valid email address.'] } } },
    { primary_registrant: { email: ['Enter a valid email address.'] }, internal_debug: 'private-debug', access_token: 'private-token' },
    ['DIC registration is not currently open.'],
  ]
  const expected = [/Account: This password is entirely numeric/, /Participant 2 — Email: Enter a valid email address/, /Participant 2 — Email: Enter a valid email address/, /Booking contact — Email: Enter a valid email address/, /DIC registration is not currently open/]
  try {
    for (let index = 0; index < bodies.length; index++) {
      const calls = []
      globalThis.fetch = async (url, options) => { calls.push({ url, options }); return Response.json(bodies[index], { status: 400 }) }
      await assert.rejects(createRegistrationOrder({ portal_account: { password: 'private-password' } }, 'same-key'), error => {
        assert.equal(error.statusCode, 400)
        assert.match(error.message, expected[index])
        assert.doesNotMatch(error.message, /HTTP 400|private-/)
        return true
      })
      assert.equal(calls.length, 1)
      assert.equal(calls[0].options.headers['Idempotency-Key'], 'same-key')
      assert.equal(calls[0].options.credentials, 'omit')
    }
  } finally { globalThis.fetch = original }
})

test('unknown or non-JSON order errors retain a bounded generic fallback', async () => {
  const original = globalThis.fetch
  try {
    for (const response of [Response.json({ unknown_secret: 'private-token' }, { status: 400 }), new Response('<html>private-debug</html>', { status: 400 })]) {
      globalThis.fetch = async () => response
      await assert.rejects(createRegistrationOrder({}, 'same-key'), error => {
        assert.equal(error.statusCode, 400)
        assert.match(error.message, /HTTP 400/)
        assert.doesNotMatch(error.message, /private-/)
        return true
      })
    }
  } finally { globalThis.fetch = original }
})

test('public requests retain bearer-only behavior without session cookies', async () => {
  const original = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return Response.json({ payment_status: 'pending' })
  }
  try {
    await initializePayment('test-order', 'private-order-token')
    await getRegistrationOrder('test-order', 'private-order-token')
    assert.equal(calls.length, 2)
    for (const { options } of calls) {
      assert.equal(options.credentials, 'omit')
      assert.equal(options.headers.Authorization, 'Bearer private-order-token')
      assert.equal(options.headers['X-CSRFToken'], undefined)
    }
  } finally { globalThis.fetch = original }
})

test('staging rejection retries with existing session and fresh CSRF, preserving order idempotency', async () => {
  const original = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/csrf/')) return Response.json({ csrfToken: 'csrf-test-only' })
    if (options.credentials === 'omit') return Response.json({ code: 'staging_tester_required' }, { status: 403 })
    return Response.json({ order_id: 'test-order' })
  }
  try {
    const payload = { participants: [{ full_name: 'Synthetic participant' }] }
    await createRegistrationOrder(payload, 'same-test-key')
    assert.equal(calls.length, 3)
    assert.ok(calls[1].url.endsWith('/dic/operations/auth/csrf/'))
    assert.equal(calls[1].options.credentials, 'include')
    assert.equal(calls[2].options.credentials, 'include')
    assert.equal(calls[2].options.headers['X-CSRFToken'], 'csrf-test-only')
    assert.equal(calls[2].options.headers['Idempotency-Key'], 'same-test-key')
    assert.equal(calls[2].options.body, calls[0].options.body)
  } finally { globalThis.fetch = original }
})

test('staging payment retry keeps bearer token and stops after one session attempt', async () => {
  const original = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/csrf/')) return Response.json({ csrfToken: 'csrf-test-only' })
    return Response.json({ code: 'staging_tester_required', detail: 'Tester login required' }, { status: 403 })
  }
  try {
    await assert.rejects(verifyPayment('order', 'reference', 'private-token'), /Tester login required/)
    assert.equal(calls.length, 3)
    assert.equal(calls[2].options.headers.Authorization, 'Bearer private-token')
  } finally { globalThis.fetch = original }
})

test('ordinary permission errors do not trigger cookie-based retries', async () => {
  const original = globalThis.fetch
  let count = 0
  globalThis.fetch = async () => {
    count += 1
    return Response.json({ detail: 'Forbidden' }, { status: 403 })
  }
  try {
    await assert.rejects(initializePayment('order', 'token'), /Forbidden/)
    assert.equal(count, 1)
  } finally { globalThis.fetch = original }
})

test('successful but malformed registration responses never become assumed order or payment success', async () => {
  const original = globalThis.fetch
  try {
    for (const body of [null, [], 'paid', true]) {
      let calls = 0
      globalThis.fetch = async () => { calls++; return Response.json(body) }
      await assert.rejects(createRegistrationOrder({ participants: [] }, 'synthetic-same-key'), error => {
        assert.equal(error.statusCode, 200)
        assert.match(error.message, /unreadable response/)
        assert.equal(error.body, null)
        return true
      })
      assert.equal(calls, 1)
    }
  } finally { globalThis.fetch = original }
})
