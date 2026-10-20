import test from 'node:test'
import assert from 'node:assert/strict'
import { createRegistrationOrder, initializePayment, verifyPayment, getRegistrationOrder } from './dicApi.js'

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
