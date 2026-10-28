export const financeSections = ['Overview', 'Registration revenue', 'Other income', 'Expenses', 'Budgets', 'Reconciliation', 'Reports']
export function receivedKobo(summary = {}) {
  const values = [summary.registration_revenue_kobo, summary.other_income_kobo]
  if (!values.every(Number.isSafeInteger)) return null
  const total = values[0] + values[1]
  return Number.isSafeInteger(total) ? total : null
}

// Presentation of already authorized, loaded rows only; never a second ledger.
export function recentFinanceRows(payments = [], entries = []) {
  return [
    ...payments.map(row => ({ id: `payment-${row.id}`, source: 'Online registration',
      amount_kobo: row.verified_kobo, date: row.date,
      status: row.verified_kobo > 0 ? 'Received' : `Not received (${row.excluded_reason || row.status})`, record: row })),
    ...entries.map(row => ({ id: `entry-${row.id}`, source: row.kind === 'income' ? 'Other income' : 'Expense',
      amount_kobo: row.amount_kobo, date: row.date, status: row.status, record: row })),
  ].sort((a, b) => String(b.date).localeCompare(String(a.date)) || a.id.localeCompare(b.id)).slice(0, 10)
}
export function naira(kobo) {
  if (!Number.isSafeInteger(kobo)) return 'Unavailable'
  return new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(kobo / 100)
}
export function financePath(edition, filters = {}) {
  if (!/^[1-9]\d*$/.test(String(edition))) throw new Error('Choose a camp edition.')
  return `/finance/?${new URLSearchParams({ edition: String(edition), ...filters })}`
}
export function entryActions(entry, permissions) {
  const result = []
  if (entry.status === 'draft' && permissions[entry.kind === 'income' ? 'record_income' : 'submit_expense']) result.push('submit')
  if (entry.status === 'submitted' && permissions.approve) result.push('approve', 'reject')
  if (entry.status === 'approved' && entry.kind === 'expense' && permissions.confirm_payment) result.push('pay')
  if (['draft', 'submitted'].includes(entry.status) && permissions.approve) result.push('cancel')
  if (['approved', 'paid'].includes(entry.status) && permissions.reconcile) result.push('reverse')
  return result
}
