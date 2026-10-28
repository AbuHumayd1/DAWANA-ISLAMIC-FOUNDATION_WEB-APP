import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { checkInPath, checkInTime } from './checkIn.js'
import { visibleOperationsGroups } from './operationsNavigation.js'

let server, Results
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Results = (await server.ssrLoadModule('/src/pages/CampCheckIn.jsx')).CheckInResults
})
after(async () => { await server?.close() })
const person = (values = {}) => ({ participant_id: 'synthetic-1', name: 'Aisha <Test>', registration_number: 'REG-TEST', participant_number: 'DIC-TEST',
  registration_status: 'confirmed', payment_status: 'paid', eligibility: { eligible: true, label: 'Verified and eligible' }, house: null, check_in: null, ...values })
const render = (row, values = {}) => renderToStaticMarkup(createElement(Results, { rows: [row], canCheckIn: true, busy: '', onCheckIn() {}, ...values }))

test('check-in search and pagination encode values and reject invalid edition/page', () => {
  const path = checkInPath('41', ' Aisha & Musa ', 2)
  const query = new URL(`https://example.test${path}`).searchParams
  assert.equal(query.get('edition'), '41')
  assert.equal(query.get('search'), 'Aisha & Musa')
  assert.equal(query.get('page'), '2')
  for (const edition of ['../', '0', '-1', 'a&b']) assert.throws(() => checkInPath(edition))
  for (const page of [0, -1, NaN, 1.5]) assert.throws(() => checkInPath('41', '', page))
  assert.throws(() => checkInPath('41', 'a'.repeat(201)))
})

test('Camp Check-in navigation appears once only for campsite staff', () => {
  const links = access => visibleOperationsGroups({ can_access_campsite: access, permissions: {} }).flatMap(group => group.items)
  assert.equal(links(false).filter(item => item.to.endsWith('/check-in')).length, 0)
  const allowed = links(true).filter(item => item.to.endsWith('/check-in'))
  assert.equal(allowed.length, 1)
  assert.equal(allowed[0].label, 'Camp Check-in')
  assert.equal(allowed[0].planned, undefined)
})

test('eligible pending-house participant has action and escaped participant data', () => {
  const markup = render(person())
  assert.match(markup, /Pending assignment/)
  assert.match(markup, />Check In<\/button>/)
  assert.doesNotMatch(markup, /disabled=""/)
  assert.match(markup, /Aisha &lt;Test&gt;/)
  assert.match(markup, /Registration: REG-TEST/)
  assert.match(markup, /Participant ID: DIC-TEST/)
})

test('ineligible or busy participant cannot use the action; view-only staff have no action', () => {
  const ineligible = person({ eligibility: { eligible: false, label: 'Payment evidence needs review' } })
  assert.match(render(ineligible), /disabled=""/)
  assert.match(render(ineligible), /Payment evidence needs review/)
  assert.match(render(person(), { busy: 'synthetic-1' }), /Checking in…/)
  assert.match(render(person(), { busy: 'another-person' }), /disabled=""/)
  const viewOnly = render(person(), { canCheckIn: false })
  assert.doesNotMatch(viewOnly, /<button/)
  assert.match(viewOnly, /Check-in permission required/)
})

test('existing arrival shows original time and staff without another check-in button', () => {
  const markup = render(person({ house: 'House One', check_in: { time: '2026-12-20T08:30:00Z', staff: 'Arrival Staff' } }))
  assert.match(markup, /Checked In/)
  assert.match(markup, /By Arrival Staff/)
  assert.match(markup, /House One/)
  assert.doesNotMatch(markup, /<button/)
  assert.match(checkInTime('2026-12-20T08:30:00Z'), /09:30|9:30/)
})
