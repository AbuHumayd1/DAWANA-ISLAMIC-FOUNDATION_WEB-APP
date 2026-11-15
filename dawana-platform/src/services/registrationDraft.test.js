import test from 'node:test'
import assert from 'node:assert/strict'
import { privateDraft } from './productionContract.js'
import { clearRegistrationDraft, paymentProtectionRequired, retainedRegistrationDraft } from './registrationDraft.js'

test('known pre-payment drafts clear even with an unused order or uncertain order submission', () => {
  for (const stale of [false, true]) {
    const saved = privateDraft({ draftVersion: 2, paymentRequested: false, orderId: 'unused-order', submissionUncertain: true,
      paymentStatus: 'pending', expiresAt: stale ? 1 : Date.now()+60000, idempotencyKey: 'synthetic-key' })
    assert.equal(paymentProtectionRequired(saved), false)
    assert.equal(retainedRegistrationDraft(saved), null)
    assert.equal(JSON.stringify(saved).includes('password'), false)
  }
})

test('payment request boundary, response uncertainty and verified payments survive local expiry', () => {
  for (const data of [{ paymentRequested: true }, { paymentReference: 'synthetic-ref' }, { authorizationUrl: 'https://checkout.paystack.com/synthetic' }, { paymentStatus: 'paid' }]) {
    const saved = privateDraft({ draftVersion: 2, orderId: 'protected-order', expiresAt: 1, ...data })
    assert.equal(saved.paymentRequested, true)
    assert.equal(retainedRegistrationDraft(saved), saved)
  }
})

test('ambiguous legacy order hints are never silently labelled never-initiated', () => {
  const legacy = { orderId: 'legacy-order', paymentStatus: 'pending', expiresAt: 1 }
  assert.equal(paymentProtectionRequired(legacy), true)
  assert.equal(paymentProtectionRequired(privateDraft(legacy)), true)
  assert.equal(retainedRegistrationDraft({ participants: [], expiresAt: 1 }), null)
})

test('explicit fresh registration clears only the draft key and never account or payment authority', () => {
  const storage = new Map([['dawana.dic.registration.v1', 'old-order'], ['account', 'preserved'], ['other', 'preserved']])
  assert.equal(clearRegistrationDraft({removeItem: key => storage.delete(key)}), true)
  assert.deepEqual([...storage], [['account', 'preserved'], ['other', 'preserved']])
  assert.equal(clearRegistrationDraft({removeItem: () => { throw new Error('storage unavailable') }}), false)
})
