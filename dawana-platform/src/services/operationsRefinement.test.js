import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { navigation, visibleOperationsNavigation, visibleOperationsGroups } from './operationsNavigation.js'

let server, pages, Nav, Metrics, MoreFilters, FilterActions
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  pages = await server.ssrLoadModule('/src/pages/Operations.jsx')
  Nav = (await server.ssrLoadModule('/src/components/operations/OperationsNavigation.jsx')).default
  Metrics = (await server.ssrLoadModule('/src/pages/CampsiteFoundation.jsx')).CampsiteMetrics
  const controls = await server.ssrLoadModule('/src/components/operations/OperationsControls.jsx')
  MoreFilters = controls.MoreFilters; FilterActions = controls.FilterActions
})
after(async () => { await server?.close() })
const user = { can_access_campsite: true, permissions: { finance: true, ids: true, manage_ids: true, export_reports: true, audit: true, scores: true } }
const render = (Component, props = {}, route = '/dic/operations') => renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: [route] }, createElement(Component, props)))

test('grouping preserves every allowed route once for all combinations of existing permissions', () => {
  for (let mask = 0; mask < 8192; mask++) {
    const permissions = Object.fromEntries(['finance','ids','manage_ids','export_reports','audit','scores','feedback','feedback_entry','welfare','timetables','classes','announcements'].map((key,index) => [key, !!(mask & (1 << index))]))
    const profile = { permissions, can_access_campsite: !!(mask & 4096) }
    const flat = visibleOperationsNavigation(profile).map(item => item.to).sort()
    const grouped = visibleOperationsGroups(profile).flatMap(group => group.items.map(item => item.to)).sort()
    assert.deepEqual(grouped, flat)
    assert.equal(new Set(grouped).size, grouped.length)
  }
  assert.deepEqual(visibleOperationsGroups(user).map(group => group.label), ['Camp Overview','Participants & Registration','Camp Activities','Finance & Reports','Administration'])
  assert.equal(navigation.length, 21)
  assert.equal(navigation.filter(item => item.to === '/dic/operations/check-in').length, 1)
})

test('sidebar renders semantic headings, current-page state and planned badges without forbidden links', () => {
  const markup = render(Nav, { user, onSelect: () => {} }, '/dic/operations/finance')
  for (const label of ['Camp Overview','Participants &amp; Registration','Camp Activities','Finance &amp; Reports','Administration']) assert.ok(markup.includes(label))
  assert.equal((markup.match(/aria-current="page"/g) || []).length, 1)
  assert.equal((markup.match(/class="campsite-planned"/g) || []).length, 0)
  const restricted = render(Nav, { user: { permissions: {}, can_access_campsite: true } })
  for (const path of ['/finance','/payments','/activity','/id-printing','/participant-ids','/reports','/scoring','/feedback','/feedback-submit','/welfare']) assert.equal(restricted.includes(`href="/dic/operations${path}"`), false)
})

test('overview keeps exact metric definitions available while showing short cards and unavailable attendance', () => {
  const keys = ['registered_participants','eligible_participants','awaiting_payment_verification','assigned_participants','awaiting_house_assignment','active_ids','requiring_attention','attendance']
  const definitions = Object.fromEntries(keys.map(key => [key, `Exact definition for ${key}`]))
  const markup = render(Metrics, { metrics: { registered_participants: 0, active_ids: 12, attendance: null }, definitions })
  for (const definition of Object.values(definitions)) assert.ok(markup.includes(definition))
  assert.match(markup, /<strong>0<\/strong>/)
  assert.match(markup, /<strong>12<\/strong>/)
  assert.match(markup, /<strong>Unavailable<\/strong>/)
  assert.match(markup, /<details class="ops-help"><summary>About these figures/)
  assert.doesNotMatch(markup, /<details[^>]* open/)
  assert.match(markup, /do not confirm that someone has arrived/)
})

test('secondary filters remain mounted with values and accessible apply and clear actions', () => {
  const markup = render(MoreFilters, { children: createElement('label', null, 'From', createElement('input', { type: 'date', defaultValue: '2026-12-23', name: 'date_from' })) })
  assert.match(markup, /<summary>More filters<\/summary>/)
  assert.match(markup, /type="date"[^>]*name="date_from"[^>]*value="2026-12-23"/)
  assert.doesNotMatch(markup, /<details[^>]* open|disabled=/)
  const actions = render(FilterActions, { onClear: () => {} })
  assert.match(actions, /type="submit">Apply filters/)
  assert.match(actions, /type="button">Clear filters/)
})

test('registration participant and payment pages preserve primary search and all filters in compact sections', () => {
  for (const component of [pages.RegistrationListPage, pages.ParticipantListPage, pages.PaymentsPage]) {
    const markup = render(component)
    assert.match(markup, /aria-label="Search"/)
    assert.match(markup, /<summary>More filters<\/summary>/)
    for (const field of ['Payment status','Category','House','From','To']) assert.ok(markup.includes(field))
    assert.match(markup, /Apply filters/)
    assert.match(markup, /Clear filters/)
  }
  const filtered = render(pages.RegistrationListPage, {}, '/dic/operations/registrations?q=Example&house=7&date_from=2026-12-23')
  assert.match(filtered, /value="Example"/)
  assert.match(filtered, /value="2026-12-23"/)
})

test('reports preserve Word and CSV choices and gated report types with collapsed optional filters', () => {
  const markup = render(pages.ReportsPage, { user })
  assert.match(markup, /<summary>Optional report filters<\/summary>/)
  assert.match(markup, /\.docx/); assert.match(markup, /\.csv/)
  assert.match(markup, /aria-pressed="true"/)
  assert.match(markup, /Download DOCX/)
  assert.doesNotMatch(markup, /\.xlsx|Download PDF/)
  const restricted = render(pages.ReportsPage, { user: { permissions: { export_reports: true } } })
  assert.doesNotMatch(restricted, /<option value="payments"/)
  const source = fs.readFileSync(new URL('../pages/Operations.jsx', import.meta.url), 'utf8')
  assert.match(source, /downloadOperationsReport\({ report, format, filters }\)/)
  assert.match(source, /setActive\(next\)/)
})

test('refined styles cover tablet and small mobile without body scroll locking or focus removal', () => {
  const css = fs.readFileSync(new URL('../pages/Operations.css', import.meta.url), 'utf8')
  assert.match(css, /\.ops-app :focus-visible/)
  assert.match(css, /@media \(prefers-reduced-motion:reduce\)/)
  assert.match(css, /\.ops-nav-group-links { grid-template-columns:minmax\(0,1fr\)/)
  assert.match(css, /\.ops-filter-actions > button { flex:1 1 130px/)
  assert.doesNotMatch(css, /body\s*{[^}]*overflow\s*:\s*hidden/)
})
