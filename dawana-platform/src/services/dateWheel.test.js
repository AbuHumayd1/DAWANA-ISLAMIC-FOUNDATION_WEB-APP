import test from 'node:test'
import assert from 'node:assert/strict'
import { daysInMonth, wheelClamp, wheelChoices, wheelISO, wheelParts } from '../components/dic/dateWheel.js'

test('DOB wheel preserves YYYY-MM-DD values without UTC date shifting', () => {
  assert.deepEqual(wheelParts('2020-02-29'),[2020,2,29])
  assert.equal(wheelISO(2008,1,9),'2008-01-09')
  assert.equal(wheelParts('2021-02-29'),null)
})
test('DOB wheel correctly handles leap years and day clamping on month/year changes', () => {
  assert.equal(daysInMonth(2024,2),29)
  assert.equal(daysInMonth(2023,2),28)
  assert.deepEqual(wheelClamp([2023,2,31],'1900-01-01','2026-11-16'),[2023,2,28])
  assert.deepEqual(wheelClamp([2024,2,31],'1900-01-01','2026-11-16'),[2024,2,29])
})
test('DOB wheel respects inclusive registration date bounds', () => {
  assert.deepEqual(wheelClamp([2026,12,31],'1900-01-01','2026-11-16'),[2026,11,16])
  assert.deepEqual(wheelClamp([1899,12,12],'1900-01-01','2026-11-16'),[1900,1,1])
  const atMaximum=wheelChoices([2026,11,16],'1900-01-01','2026-11-16')
  assert.equal(atMaximum.months.at(-1),11)
  assert.equal(atMaximum.days.at(-1),16)
  assert.deepEqual(wheelChoices([2024,2,15],'1900-01-01','2026-11-16').days.at(-1),29)
})
