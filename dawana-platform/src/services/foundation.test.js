import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { safeDonationCheckout, donationMessage, newDonationRequest, foundationRequest } from './foundation.js'

test('donation checkout permits only trusted Paystack HTTPS targets', () => {
  assert(safeDonationCheckout('https://checkout.paystack.com/test'))
  for (const value of ['javascript:alert(1)', 'https://checkout.paystack.com.evil.test', 'http://checkout.paystack.com', 'https://user@checkout.paystack.com', 'https://checkout.paystack.com:444']) assert.equal(safeDonationCheckout(value), false)
})
test('donation states distinguish confirmation, pending, failure and review', () => {
  assert.match(donationMessage('successful'), /verified/)
  assert.match(donationMessage('failed'), /No successful/)
  assert.match(donationMessage('abandoned'), /No successful/)
  assert.match(donationMessage('pending'), /pending/)
  assert.match(donationMessage('review'), /Do not pay again/)
})
test('donation request identities are random and amounts preserve decimal strings', () => {
  const one = newDonationRequest('donor@example.test', '0.01'), two = newDonationRequest('donor@example.test', '0.01')
  assert.notEqual(one.request_id, two.request_id); assert.notEqual(one.access_token, two.access_token)
  assert.match(one.access_token, /^[a-f0-9]{64}$/); assert.equal(one.amount, '0.01')
})
test('foundation requests use CSRF and separate donation bearer headers', async () => {
  const original = globalThis.fetch, requests = []
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options })
    return new Response(JSON.stringify(url.endsWith('/csrf/') ? { csrfToken: 'synthetic-csrf' } : { received: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await foundationRequest('/donations/synthetic/', { body: {}, token: 'synthetic-token' })
    assert.match(requests[0].url, /\/foundation\/csrf\/$/)
    assert.equal(requests[1].options.headers['X-CSRFToken'], 'synthetic-csrf')
    assert.equal(requests[1].options.headers['X-Donation-Token'], 'synthetic-token')
    assert.equal(requests[1].options.credentials, 'include')
    assert(!requests[1].url.includes('synthetic-token'))
  } finally { globalThis.fetch = original }
})
test('operator-confirmed contact channels are exact and WhatsApp is not inferred', () => {
  const data = JSON.parse(fs.readFileSync(new URL('../../../backend/dic/data/foundation_contact.json', import.meta.url)))
  assert.equal(data.email, 'dawanaislamicfoundation@gmail.com')
  assert.deepEqual(data.phones, ['+2347062956559', '+2348105320528', '+2349018076534'])
  assert.equal(data.whatsapp, undefined)
})
