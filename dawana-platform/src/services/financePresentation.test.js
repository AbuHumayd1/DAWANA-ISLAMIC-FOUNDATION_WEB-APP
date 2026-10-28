import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

let server, Overview, EntryForm
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  const module = await server.ssrLoadModule('/src/pages/Finance.jsx')
  Overview = module.FinanceOverview; EntryForm = module.FinanceEntryForm
})
after(async () => { await server?.close() })
const summary = { registration_revenue_kobo: 10000, other_income_kobo: 3000,
  expenditure_kobo: 2000, net_position_kobo: 11000, approved_unpaid_kobo: 5000,
  approved_budget_kobo: 20000, remaining_budget_kobo: 18000 }
const render = (component, props) => renderToStaticMarkup(createElement(component, props))

test('simple overview shows three cash figures and keeps budgets outside cash cards', () => {
  const html = render(Overview, { summary, permissions: { view_details: true, record_income: true, submit_expense: true } })
  assert.equal((html.match(/<article>/g) || []).length, 3)
  for (const label of ['Money Received', 'Money Spent', 'Recorded Net Position', 'Add Money In', 'Record Expense', 'Recent transactions']) assert.ok(html.includes(label))
  for (const amount of ['130.00', '20.00', '110.00']) assert.ok(html.includes(amount))
  assert.match(html, /Online registration payments appear automatically/)
  assert.match(html, /not a reconciled bank balance/)
  assert.match(html, /<details[^>]*><summary>Approvals, budgets/)
})

test('summary-only view disables entry actions and never renders supplied confidential rows', () => {
  const html = render(Overview, { summary: {}, permissions: {},
    entries: [{ id: 'private', title: 'confidential', kind: 'income', amount_kobo: 12345, date: '2026-01-01', status: 'approved' }] })
  assert.match(html, /disabled=""[^>]*>Add Money In/)
  assert.match(html, /disabled=""[^>]*>Record Expense/)
  assert.doesNotMatch(html, /123\.45|confidential/)
  assert.match(html, /Unavailable/)
})

test('recording forms preserve required backend fields and draft workflow with optional evidence', () => {
  for (const kind of ['income', 'expense']) {
    const html = render(EntryForm, { kind, categories: [{ id: 1, name: 'Approved category', active: true, kind }] })
    for (const name of ['category', 'title', 'amount', 'date', 'method', 'reference', 'reason']) {
      const tag = html.match(new RegExp(`<(?:input|select|textarea)\\b[^>]*name="${name}"[^>]*>`))?.[0]
      assert.ok(tag, `Missing ${name}`)
      assert.match(tag, /required=""/)
    }
    assert.match(html, /Save draft for review/)
    assert.match(html, /<details[^>]*><summary>Extra details and payment evidence/)
    assert.match(html, /Amount \(NGN\)/)
    if (kind === 'income') assert.match(html, /Online payments are added automatically/)
    else assert.match(html, /Saving or approval does not mark it paid/)
  }
  const html = render(EntryForm, { kind: 'expense', categories: [] })
  assert.match(html, /disabled=""[^>]*>Save draft for review/)
  assert.match(html, /authorized budget manager/)
})
