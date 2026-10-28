import test from 'node:test'
import assert from 'node:assert/strict'
import { financePath, naira, entryActions, financeSections, receivedKobo, recentFinanceRows } from './finance.js'

test('finance paths require an edition and encode filters', () => {
  for (const id of ['', '0', '-1', 'a&b']) assert.throws(() => financePath(id))
  assert.equal(financePath(2, { q: 'x&y' }), '/finance/?edition=2&q=x%26y')
})
test('finance formats exact kobo and never invents unavailable totals', () => {
  assert.match(naira(12345), /123\.45/)
  assert.match(naira(-100), /1\.00/)
  assert.equal(naira(null), 'Unavailable')
})
test('expense approval and cash confirmation are independent', () => {
  assert.deepEqual(entryActions({ status: 'submitted', kind: 'expense' }, {}), [])
  assert.deepEqual(entryActions({ status: 'submitted', kind: 'expense' }, { approve: true }), ['approve', 'reject', 'cancel'])
  assert.deepEqual(entryActions({ status: 'approved', kind: 'expense' }, { confirm_payment: true }), ['pay'])
  assert.deepEqual(entryActions({ status: 'approved', kind: 'income' }, { confirm_payment: true }), [])
})
test('paid entries can only be reversed with reconciliation authority', () => {
  assert.deepEqual(entryActions({ status: 'paid', kind: 'expense' }, { approve: true }), [])
  assert.deepEqual(entryActions({ status: 'paid', kind: 'expense' }, { reconcile: true }), ['reverse'])
})
test('finance offers all operational subsections within the existing module', () => {
  assert.equal(financeSections.length, 7)
  assert.ok(financeSections.includes('Reconciliation'))
  assert.ok(financeSections.includes('Budgets'))
})

test('received display combines only backend receipt totals and refuses unavailable or unsafe values', () => {
  assert.equal(receivedKobo({ registration_revenue_kobo: 10001, other_income_kobo: 234 }), 10235)
  assert.equal(receivedKobo({ registration_revenue_kobo: 0, other_income_kobo: 0 }), 0)
  assert.equal(receivedKobo({}), null)
  assert.equal(receivedKobo({ registration_revenue_kobo: 100, other_income_kobo: null }), null)
  assert.equal(receivedKobo({ registration_revenue_kobo: Number.MAX_SAFE_INTEGER, other_income_kobo: 1 }), null)
})

test('recent rows retain server-verified adjusted income and original workflow statuses without mutating records', () => {
  const payment = { id: 'p', date: '2026-01-01', amount_kobo: 10000, verified_kobo: 8000, status: 'successful' }
  const pending = { id: 'q', date: '2026-01-03', amount_kobo: 90000, verified_kobo: 0, status: 'pending', excluded_reason: 'order_not_paid' }
  const expense = { id: 'e', date: '2026-01-02', kind: 'expense', amount_kobo: 2000, status: 'approved' }
  const before = JSON.stringify([payment, pending, expense])
  const rows = recentFinanceRows([payment, pending], [expense])
  assert.deepEqual(rows.map(row => row.date), ['2026-01-03', '2026-01-02', '2026-01-01'])
  assert.equal(rows[0].amount_kobo, 0)
  assert.match(rows[0].status, /Not received/)
  assert.equal(rows[1].status, 'approved')
  assert.equal(rows[2].amount_kobo, 8000)
  assert.equal(rows[2].record, payment)
  assert.equal(JSON.stringify([payment, pending, expense]), before)
  assert.deepEqual(recentFinanceRows(), [])
  assert.equal(recentFinanceRows([], Array.from({ length: 12 }, (_, id) => ({ ...expense, id }))).length, 10)
})
