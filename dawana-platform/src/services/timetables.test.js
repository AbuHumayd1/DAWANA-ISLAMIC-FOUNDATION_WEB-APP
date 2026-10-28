import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import { adjacentDate, timetablePath } from './timetables.js'

test('timetable requests are tied to booking items and the two supported types', () => {
  assert.equal(timetablePath(42, 'food', '2027-01-01'), '/timetables/?item_id=42&type=food&date=2027-01-01')
  for (const item of [0, -1, '1&edition=9']) assert.throws(() => timetablePath(item, 'activities'))
  assert.throws(() => timetablePath(1, 'house'))
  assert.throws(() => timetablePath(1, 'activities', '<script>'))
})
test('previous and next navigation crosses years and respects camp boundaries', () => {
  const dates = [{ date: '2026-12-31' }, { date: '2027-01-01' }]
  assert.equal(adjacentDate(dates, '2026-12-31', 1), '2027-01-01')
  assert.equal(adjacentDate(dates, '2027-01-01', -1), '2026-12-31')
  assert.equal(adjacentDate(dates, '2027-01-01', 1), '')
})
test('authoritative draft data preserves two timetables, ten days and amendments', () => {
  const { entries } = JSON.parse(fs.readFileSync(new URL('../../../backend/dic/data/dic2026_timetables.json', import.meta.url)))
  assert.deepEqual([...new Set(entries.map(row => row.timetable_type))].sort(), ['activities', 'food'])
  for (const type of ['activities', 'food']) assert.equal(new Set(entries.filter(row => row.timetable_type === type).map(row => row.date)).size, 10)
  const day6 = entries.filter(row => row.day_number === 6 && row.timetable_type === 'activities')
  assert(day6.some(row => row.description === 'Health Forum / Health Symposium' && row.start_time === '11:00' && row.end_time === '13:00'))
  assert(day6.some(row => row.description === 'Sports Activities' && row.start_time === '17:00' && row.end_time === '18:30'))
  assert(!day6.some(row => /proposed|optional/i.test(row.description)))
  assert(entries.filter(row => row.timetable_type === 'food').every(row => row.start_time === null && row.end_time === null))
  assert.equal(entries.filter(row => row.timetable_type === 'food' && !row.description.trim()).length, 3)
  assert(entries.some(row => row.date === '2026-12-24' && row.description === 'Official Camp Opening Session' && row.start_time === '09:00' && row.end_time === '11:00'))
  assert(entries.some(row => row.date === '2026-12-24' && row.description === 'Basic Islam: Qur’an / Aqeedah' && row.start_time === '11:00' && row.end_time === '13:00'))
  assert(entries.some(row => row.date === '2026-12-31' && row.description === 'Sisters’ Workshop / Brothers’ Activity'))
  assert(entries.some(row => row.date === '2026-12-31' && row.description === 'Final Night'))
})
