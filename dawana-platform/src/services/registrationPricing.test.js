import test from 'node:test'
import assert from 'node:assert/strict'
import { categoryFee, estimateRegistrationTotal } from './registrationPricing.js'

test('mixed-category estimates follow category changes and removal without losing cents', () => {
  const categories = [{ id: 1, current_fee_ngn: '12500.25' }, { id: 2, current_fee_ngn: '8300.00' }]
  const participants = [{ categoryId: '1' }, { categoryId: '2' }]
  assert.equal(estimateRegistrationTotal(participants, categories), 20800.25)
  assert.equal(estimateRegistrationTotal([{ ...participants[0], fullName: 'Edited' }, participants[1]], categories), 20800.25)
  assert.equal(estimateRegistrationTotal([{ categoryId: '2' }, participants[1]], categories), 16600)
  assert.equal(estimateRegistrationTotal(participants.slice(0, 1), categories), 12500.25)
})

test('missing, unpriced and invalid fees make the whole estimate unavailable', () => {
  assert.equal(estimateRegistrationTotal([], []), null)
  assert.equal(estimateRegistrationTotal([{ categoryId: 99 }], []), null)
  for (const raw of [null, undefined, '', ' ', 'invalid', 'Infinity', '0', '-1']) {
    const category = { id: 2, current_fee_ngn: raw }
    assert.equal(categoryFee(category), null)
    assert.equal(estimateRegistrationTotal([{ categoryId: 1 }, { categoryId: 2 }], [
      { id: 1, current_fee_ngn: '12000.00' }, category,
    ]), null)
  }
})
