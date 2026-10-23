import test from 'node:test'
import assert from 'node:assert/strict'
import { campFeeRange, campDate } from './dicPresentation.js'

test('hero fee range uses backend prices without displaying category labels or inventing missing fees', () => {
  assert.deepEqual(campFeeRange([{ name: 'category one', current_fee_ngn: '12500.50' }, { name: 'category two', current_fee_ngn: '21000.00' }]), [12500.5, 21000])
  assert.deepEqual(campFeeRange([{ current_fee_ngn: '100' }, { current_fee_ngn: null }]), [100, 100])
  assert.equal(campFeeRange([{ current_fee_ngn: '' }, { current_fee_ngn: -3 }, { current_fee_ngn: 'invalid' }]), null)
  assert.equal(campFeeRange(), null)
})

test('camp dates use Lagos calendar dates and visitor-friendly missing states', () => {
  assert.equal(campDate('2026-12-23'), '23 Dec 2026')
  assert.equal(campDate(null), 'To be announced')
  assert.equal(campDate('invalid'), 'To be announced')
})
