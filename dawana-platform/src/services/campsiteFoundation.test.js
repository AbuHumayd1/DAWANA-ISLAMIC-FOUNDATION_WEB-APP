import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { campsiteMetricValue, campsiteModules, campsiteOverviewPath } from './campsiteModules.js'
import { visibleOperationsNavigation } from './operationsNavigation.js'

let server, PlannedModule, Finance
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  PlannedModule = (await server.ssrLoadModule('/src/pages/CampsiteFoundation.jsx')).PlannedCampsiteModule
  Finance = (await server.ssrLoadModule('/src/pages/Finance.jsx')).default
})
after(async () => { await server?.close() })

test('campsite modules have explicit future status and preserve legacy operational routes', () => {
  const limited = visibleOperationsNavigation({ can_access_campsite: true, permissions: {} })
  assert.equal(limited.some(item => item.label === 'Finance'), false)
  assert.equal(limited.some(item=>item.label==='Comprehensive reporting'),false)
  const reporting=visibleOperationsNavigation({can_access_campsite:true,permissions:{export_reports:true}})
  assert.equal(reporting.find(item=>item.label==='Comprehensive reporting')?.to,'/dic/operations/reporting-hub')
  assert.equal(reporting.find(item=>item.label==='Comprehensive reporting')?.planned,undefined)
  assert.equal(limited.some(item => item.label === 'Feedback'), false)
  assert.equal(limited.some(item => item.label === 'House scoring'), false)
  const finance = visibleOperationsNavigation({ can_access_campsite: true, permissions: { finance: true } })
  assert.equal(finance.find(item => item.label === 'Finance')?.to, '/dic/operations/finance')
  assert.equal(finance.find(item => item.label === 'Payments')?.to, '/dic/operations/payments')
  assert.equal(new Set(finance.map(item => item.to)).size, finance.length)
  assert.ok(Object.values(campsiteModules).every(module => module.implemented || (module.planned.length && module.approvals)))
})

test('unavailable metrics are never shown as zero and edition inputs are validated', () => {
  assert.equal(campsiteMetricValue(0), '0')
  assert.equal(campsiteMetricValue(240), '240')
  for (const value of [null, undefined, -1, NaN, '', '12']) assert.equal(campsiteMetricValue(value), 'Unavailable')
  assert.equal(campsiteOverviewPath('41'), '/campsite/?edition=41')
  assert.equal(campsiteOverviewPath(), '/campsite/')
  for (const value of ['../', '-1', '0', 'a&b']) assert.throws(() => campsiteOverviewPath(value))
})

test('finance loads backend data without fabricating initial balances', () => {
  const markup = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Finance)))
  assert.match(markup, /Finance sections/)
  assert.match(markup, /Reconciliation/)
  assert.doesNotMatch(markup, /₦0|Coming in a later phase/)
})

test('planning pages label incomplete capabilities without exposing confidential response forms', () => {
  for (const key of ['reporting-hub']) {
    const markup = renderToStaticMarkup(createElement(MemoryRouter, null,
      createElement(PlannedModule, { moduleKey: key, user: { permissions: {} } })))
    assert.match(markup, /Access denied/)
    assert.doesNotMatch(markup, /<form|<input|download=/)
  }
})

test('operations entry stays isolated from public layout with staff route guard and responsive flow', () => {
  const app = fs.readFileSync(new URL('../App.jsx', import.meta.url), 'utf8')
  assert.match(app, /path="\/dic\/operations\/\*" element={<Operations/)
  const operations = fs.readFileSync(new URL('../pages/Operations.jsx', import.meta.url), 'utf8')
  assert.ok(operations.indexOf('if (!user)') < operations.indexOf('<CampsiteFoundation'))
  assert.match(operations, /user.can_access_campsite \? <CampsiteFoundation/)
  assert.match(operations, /aria-expanded={menuOpen}/)
  assert.match(operations, /Escape/)
  const css = fs.readFileSync(new URL('../pages/Operations.css', import.meta.url), 'utf8')
  assert.match(css, /\.ops-main\s*{\s*min-width:0/)
  assert.match(css, /\.ops-sidebar\s*{\s*position:static; display:none/)
  assert.match(css, /\.ops-sidebar\.is-open\s*{\s*display:flex/)
  const publicChrome = fs.readFileSync(new URL('../components/layout/SiteChrome.jsx', import.meta.url), 'utf8')
  // The approved footer entry is public; the Operations workspace remains guarded.
  assert.match(publicChrome, /to="\/dic\/operations">Staff Login<\/Link>/)
  assert.doesNotMatch(publicChrome.slice(0, publicChrome.indexOf('export function Footer')), /to="\/dic\/operations"/)
})
