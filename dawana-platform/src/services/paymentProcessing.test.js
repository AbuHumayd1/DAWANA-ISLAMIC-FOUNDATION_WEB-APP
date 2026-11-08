import test from 'node:test'
import assert from 'node:assert/strict'
import { processingMessages, paystackCheckoutUrl } from './paymentReturnApi.js'

test('pending downstream work preserves payment confirmation and never requests another charge', () => {
  const paid = { payment_status: 'paid', status: 'confirmed', processing: { housing: 'pending', portal: 'delivery_pending' } }
  assert.equal(processingMessages(paid).length, 2)
  assert.match(processingMessages(paid).join(' '), /Do not pay again/)
  assert.match(processingMessages(paid).join(' '), /account is saved/)
  assert.deepEqual(processingMessages({ ...paid, payment_status: 'pending' }), [])
  assert.deepEqual(processingMessages({ ...paid, status: 'cancelled' }), [])
  assert.deepEqual(processingMessages({ ...paid, processing: { housing: 'ready', portal: 'ready' } }), [])
})

test('Pay Now navigation only accepts an absolute Paystack checkout URL', () => {
  assert.equal(paystackCheckoutUrl('https://checkout.paystack.com/checkout-code'), 'https://checkout.paystack.com/checkout-code')
  for (const value of ['https://evil.test/code', 'https://checkout.paystack.com.evil.test/code',
    'http://checkout.paystack.com/code', '//checkout.paystack.com/code',
    'https://user@checkout.paystack.com/code', 'https://checkout.paystack.com:444/code',
    'javascript:alert(1)', 'https://checkout.paystack.com/code?reference=untrusted', null]) {
    assert.equal(paystackCheckoutUrl(value), '')
  }
})
