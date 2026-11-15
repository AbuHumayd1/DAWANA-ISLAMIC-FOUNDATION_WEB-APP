import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { checkInPath } from './checkIn.js'
import { financeColumnLabel, recentFinanceRows } from './finance.js'
let server, FinanceOverview, CheckInResults
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  FinanceOverview = (await server.ssrLoadModule('/src/pages/Finance.jsx')).FinanceOverview
  CheckInResults = (await server.ssrLoadModule('/src/pages/CampCheckIn.jsx')).CheckInResults
})
after(async () => { await server?.close() })
test('check-in history path is explicit and invalid scopes fail closed', () => {
  assert.match(checkInPath(4, 'Deleted', 2, 'history'), /view=history/)
  assert.doesNotMatch(checkInPath(4), /view=/)
  assert.throws(() => checkInPath(4, '', 1, 'trash'), /active or history/)
})
test('finance headings describe rendered NGN while raw export keys stay in kobo', () => {
  assert.equal(financeColumnLabel('amount_kobo'), 'amount (NGN)')
  assert.equal(financeColumnLabel('verified_kobo'), 'verified (NGN)')
  const row={id:'paid',verified_kobo:400000,registration_state:'Deleted',status:'successful',date:'2026-11-15'}
  assert.equal(recentFinanceRows([row])[0].registration_state,'Deleted')
  assert.equal(row.verified_kobo,400000)
})
test('finance overview preserves genuine deleted-registration receipts and labels their lifecycle separately', () => {
  const html=renderToStaticMarkup(createElement(FinanceOverview, {
    summary:{registration_revenue_kobo:400000,other_income_kobo:0,net_position_kobo:400000,expenditure_kobo:0},
    permissions:{view_details:true}, payments:[{id:'paid',verified_kobo:400000,registration_state:'Deleted',status:'successful',date:'2026-11-15'}],
  }))
  assert.match(html,/4,000\.00/)
  assert.match(html,/>Deleted</)
  assert.match(html,/amount \(NGN\)/)
  assert.doesNotMatch(html,/>amount kobo</)
  assert.match(html,/deletion is not a refund/)
})
test('historical check-in rows label lifecycle and retain arrival evidence without an arrival button', () => {
  const html=renderToStaticMarkup(createElement(CheckInResults, {canCheckIn:false,rows:[{
    participant_id:'historic',name:'Historical Paid',registration_number:'booking',participant_number:'number',
    registration_lifecycle:'deleted',registration_status:'confirmed',payment_status:'paid',
    eligibility:{eligible:false,label:'Deleted registration'},check_in:{time:'2026-11-15T10:00:00Z',staff:'Authorized owner'},
  }]}))
  assert.match(html,/deleted/)
  assert.match(html,/Authorized owner/)
  assert.match(html,/Checked In/)
  assert.doesNotMatch(html,/<button/)
})
