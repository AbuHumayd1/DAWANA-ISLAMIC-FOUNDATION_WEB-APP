import test from 'node:test'
import assert from 'node:assert/strict'
import { callbackLookup, paymentReturnFailureKind, preparePaymentReturn, resolvePaymentReturn } from './paymentReturnApi.js'

test('callback parameters are bounded hints, conflicting references are rejected, and secrets are never accepted as credentials', () => {
  assert.deepEqual(callbackLookup('?reference=DICabc&trxref=DICabc&access_token=untrusted'), { reference: 'DICabc' })
  assert.deepEqual(callbackLookup('?payment_status=paid'), {})
  assert.deepEqual(callbackLookup('?reference=foreign', 'known-order'), { order_id: 'known-order' })
  for (const search of ['?reference=', '?reference=a&reference=b', '?reference=a&trxref=b', '?reference=%3Cscript%3E', `?reference=${'a'.repeat(81)}`]) assert.throws(() => callbackLookup(search))
})

test('grant preparation requires bearer plus cookie/CSRF; resolution uses cookie/CSRF without storing or forwarding a bearer', async () => {
  const original = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/csrf/')) return Response.json({ csrfToken: 'synthetic-csrf' })
    return Response.json({ ready: true })
  }
  try {
    await preparePaymentReturn('order-1', 'synthetic-private-token')
    await resolvePaymentReturn({ reference: 'DICexample' })
    assert.equal(calls.length, 4)
    for (const { options } of calls) assert.equal(options.credentials, 'include')
    assert.equal(calls[1].options.headers.Authorization, 'Bearer synthetic-private-token')
    assert.equal(calls[1].options.headers['X-CSRFToken'], 'synthetic-csrf')
    assert.equal(calls[3].options.headers.Authorization, undefined)
    assert.equal(calls[3].options.headers['X-CSRFToken'], 'synthetic-csrf')
    assert.deepEqual(JSON.parse(calls[3].options.body), { reference: 'DICexample' })
    assert.ok(calls.every(({ url }) => !url.includes('DICexample') && !url.includes('private-token')))
    assert.ok(calls.every(({ url }) => !url.includes('/initialize/')))
  } finally { globalThis.fetch = original }
})

test('expired or unauthorized sessions are surfaced without initializing or retrying payment', async () => {
  const original = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url) => {
    calls.push(url)
    return url.endsWith('/csrf/') ? Response.json({ csrfToken: 'synthetic-csrf' }) : Response.json({ detail: 'Recover the existing registration.' }, { status: 404 })
  }
  try {
    await assert.rejects(resolvePaymentReturn({ order_id: 'order-1' }), /Recover the existing registration/)
    assert.equal(calls.length, 2)
  } finally { globalThis.fetch = original }
})

test('outages, missing grants, authorization and rate limits have separate safe recovery states', () => {
  for (const status of [500, 502, 503, 504]) assert.equal(paymentReturnFailureKind({ status }), 'temporary')
  assert.equal(paymentReturnFailureKind(new TypeError('synthetic network failure')), 'temporary')
  assert.equal(paymentReturnFailureKind({ status: 404 }), 'missing')
  for (const status of [401, 403]) assert.equal(paymentReturnFailureKind({ status }), 'authorization')
  assert.equal(paymentReturnFailureKind({ status: 429 }), 'limited')
})
