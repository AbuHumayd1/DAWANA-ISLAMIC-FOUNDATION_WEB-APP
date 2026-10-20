import test from 'node:test'
import assert from 'node:assert/strict'
import { occupations, maritalOptions, participantChoiceLabel } from '../components/dic/participantOptions.js'

test('explicit nonempty None choice preserves all existing choices and readable display', () => {
  assert.deepEqual(occupations.slice(0, -1), ['Civil Servant', 'Business', 'Trader', 'Entrepreneur'])
  assert.deepEqual(maritalOptions.slice(0, -1), ['Single', 'Married', 'Divorcee', 'Widow / Widower'])
  for (const options of [occupations, maritalOptions]) {
    assert.deepEqual(options.at(-1), { value: 'None', label: 'None (Not applicable)' })
    assert.notEqual(options.at(-1).value, '')
  }
  assert.equal(participantChoiceLabel('None'), 'None (Not applicable)')
  assert.equal(participantChoiceLabel('Business'), 'Business')
  assert.equal(participantChoiceLabel('Single'), 'Single')
})
