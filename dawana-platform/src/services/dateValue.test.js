import test from 'node:test'
import assert from 'node:assert/strict'
import { boundDate, calendarKey, changeMonth, dateError, dateValue, parseDate } from '../components/dic/dateValue.js'

test('strict ISO birth dates reject rollover, incomplete input and invalid leap days', () => {
  for (const invalid of ['', '2026-2-01', '2026-02-30', '2025-02-29', '1900-02-29', '0000-01-01', '2026-13-01', '2026-00-01', '2026-01-00', 'not a date']) assert.equal(parseDate(invalid), null, invalid)
  for (const valid of ['2024-02-29', '2000-02-29', '0001-01-01', '0099-12-31', '2012-01-01']) assert.equal(dateValue(parseDate(valid)), valid)
})

test('date boundaries are inclusive, including exact birthday/age limits supplied by the form', () => {
  const min = '2008-10-20', max = '2018-10-20'
  assert.equal(dateError(min, min, max), '')
  assert.equal(dateError(max, min, max), '')
  assert.match(dateError('2008-10-19', min, max), /on or after/)
  assert.match(dateError('2018-10-21', min, max), /on or before/)
  assert.match(dateError('2026-10-21', undefined, '2026-10-20'), /on or before/)
  assert.match(dateError('2025-02-29'), /valid date/)
  assert.equal(dateError(''), '')
  assert.equal(dateValue(boundDate(parseDate('2010-02-01'), min, max)), '2010-02-01')
})

test('month and year navigation clamp leap days and month ends without rolling forward', () => {
  assert.equal(dateValue(changeMonth(parseDate('2024-01-31'), 1)), '2024-02-29')
  assert.equal(dateValue(changeMonth(parseDate('2024-02-29'), 12)), '2025-02-28')
  assert.equal(dateValue(changeMonth(parseDate('2026-01-31'), -1)), '2025-12-31')
})

test('calendar keys move by day/week/month/year and stop at supplied limits', () => {
  const min = '2000-01-01', max = '2026-10-20'
  const move = (value, key, shift = false) => dateValue(calendarKey(parseDate(value), key, shift, min, max))
  assert.equal(move('2024-02-28', 'ArrowRight'), '2024-02-29')
  assert.equal(move('2024-02-29', 'ArrowDown'), '2024-03-07')
  assert.equal(move('2024-02-29', 'Home'), '2024-02-25')
  assert.equal(move('2024-02-29', 'End'), '2024-03-02')
  assert.equal(move('2024-02-29', 'PageDown', true), '2025-02-28')
  assert.equal(move(max, 'ArrowRight'), max)
  assert.equal(move(min, 'ArrowLeft'), min)
  assert.equal(calendarKey(parseDate(max), 'Tab', false, min, max), null)
})
