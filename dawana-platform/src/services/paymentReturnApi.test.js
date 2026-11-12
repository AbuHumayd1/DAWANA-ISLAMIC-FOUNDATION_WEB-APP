import test from 'node:test'
import assert from 'node:assert/strict'
import { callbackLookup, paymentReturnFailureKind, preparePaymentReturn, resolvePaymentReturn, paymentReturnApiAllowed, paymentConfirmed, paymentReturnSetupMessage } from './paymentReturnApi.js'

test('failed secure return setup retries only the existing order grant with fresh CSRF', async () => {
  const original = globalThis.fetch
  const calls = []
  let tokens = 0, grants = 0
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/csrf/')) return Response.json({ csrfToken: `csrf-${++tokens}` })
    return ++grants === 1 ? Response.json({ detail: 'Payment return CSRF validation failed.' }, { status: 403 }) : Response.json({ ready: true })
  }
  try {
    await assert.rejects(preparePaymentReturn('preserved-order', 'private-token'), error => {
      assert.match(paymentReturnSetupMessage(error), /CSRF validation was refused/)
      return error.status === 403
    })
    assert.deepEqual(await preparePaymentReturn('preserved-order', 'private-token'), { ready: true })
    assert.equal(calls.length, 4)
    assert.equal(calls[1].url, calls[3].url)
    assert.equal(calls[1].options.headers['X-CSRFToken'], 'csrf-1')
    assert.equal(calls[3].options.headers['X-CSRFToken'], 'csrf-2')
    assert.ok(calls.every(({ options }) => options.credentials === 'include'))
    assert.ok(calls.every(({ url }) => !url.endsWith('/initialize/') && !url.endsWith('/orders/')))
  } finally { globalThis.fetch = original }
})

test('secure return diagnostics distinguish hosting and validation failures without exposing server data', () => {
  for (const [error, expected] of [
    [{ code: 'payment_return_origin' }, /same-site API configuration/],
    [{ status: 403 }, /CSRF validation was refused/], [{ status: 404 }, /unavailable or expired/],
    [{ status: 400 }, /server-side return session configuration/], [{ status: 429 }, /rate limited/],
    [{ status: 503 }, /service could not complete/],
  ]) {
    const message = paymentReturnSetupMessage({ ...error, message: 'private-token', body: { password: 'private-password' } })
    assert.match(message, expected)
    assert.match(message, /payment attempt is preserved/)
    assert.match(message, /No additional payment attempt/)
    assert.doesNotMatch(message, /private-/)
  }
})

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

test('payment return permits the intended HTTPS sibling API and rejects unrelated cross-site origins', () => {
  const api = 'https://api.dawanaislamicfoundation.org/api/v1'
  for (const site of ['https://dawanaislamicfoundation.org', 'https://www.dawanaislamicfoundation.org']) {
    assert.equal(paymentReturnApiAllowed(api, site + '/dic/register/payment-return'), true)
  }
  assert.equal(paymentReturnApiAllowed('/api/v1', 'http://localhost:5173/dic'), true)
  assert.equal(paymentReturnApiAllowed('https://same.example.test/api/v1', 'https://same.example.test/dic'), true)
  for (const [base, site] of [
    [api, 'https://preview.pages.dev'], [api, 'http://dawanaislamicfoundation.org'],
    ['https://dawana-islamic-foundation-web-app-1.onrender.com/api/v1', 'https://dawanaislamicfoundation.org'],
    ['http://api.dawanaislamicfoundation.org/api/v1', 'https://dawanaislamicfoundation.org'],
    ['https://api.dawanaislamicfoundation.org.evil.test/api/v1', 'https://dawanaislamicfoundation.org'],
    ['https://user@api.dawanaislamicfoundation.org/api/v1', 'https://dawanaislamicfoundation.org'],
    [api, 'https://dawanaislamicfoundation.org.evil.test'],
  ]) assert.equal(paymentReturnApiAllowed(base, site), false)
})

test('paid payment status alone cannot display a confirmed or cancelled registration as active', () => {
  assert.equal(paymentConfirmed({ payment_status: 'paid', status: 'confirmed' }), true)
  for (const order of [null, {}, { payment_status: 'paid' },
    { payment_status: 'paid', status: 'cancelled' }, { payment_status: 'refunded', status: 'confirmed' },
    { payment_status: 'pending', status: 'confirmed' }]) assert.equal(paymentConfirmed(order), false)
})
