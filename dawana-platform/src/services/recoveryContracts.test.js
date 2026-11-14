import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { experiencePayload } from './camperFeedbackForm.js'
import { getOperationsUser, signIn, getOperationsData } from './operationsApi.js'

let server, Info, Form, Editorial, Landing
before(async () => {
  server = await createServer({ configFile: false, plugins: [{
    name: 'test-landing-export',
    transform(code, id) {
      // Exercise the real internal hero without adding a production export.
      if (id.replaceAll('\\', '/').endsWith('/src/pages/DIC.jsx')) return `${code}\nexport { DICLanding as TestDICLanding }\n`
    },
  }], server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Info = (await server.ssrLoadModule('/src/components/dic/DICCampInfo.jsx')).default
  Landing = (await server.ssrLoadModule('/src/pages/DIC.jsx')).TestDICLanding
  Form = (await server.ssrLoadModule('/src/components/dic/CamperExperienceForm.jsx')).default
  Editorial = (await server.ssrLoadModule('/src/components/dic/DICEditorial.jsx')).default
})
after(async () => { await server?.close() })
const render = (component, props = {}) => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)))
const source = path => fs.readFileSync(new URL(path, import.meta.url), 'utf8')

test('daily v3 renders six authoritative questions and sends explicit version and original values', () => {
  const spec = { version: 3, ratings: { overall: 'Overall daily experience', learning: 'Classes and learning', meals: 'Food and meals', comfort: 'Accommodation and facilities', activities: 'Activities and programmes', welfare: 'Welfare and camp organisation' }, comments: { suggestions: 'Comments' }, optional_ratings: ['comfort'] }
  const ratings = [[1, 'Poor'], [2, 'Fair'], [3, 'Good'], [4, 'Very Good'], [5, 'Excellent']]
  const html = render(Form, { channel: 'daily', spec, ratings, start: '2026-12-23', end: '2027-01-01', today: '2026-12-24' })
  for (const question of Object.values(spec.ratings)) assert.ok(html.includes(question))
  assert.equal((html.match(/class="cf-rating-question"/g) || []).length, 6)
  assert.doesNotMatch(html, /Very Poor/)
  assert.ok(html.indexOf('Excellent') < html.indexOf('Very Good'))
  const payload = experiencePayload({ spec, ratings, channel: 'daily', day: '2026-12-24', choices: Object.fromEntries(Object.keys(spec.ratings).map(key => [key, key === 'comfort' ? 'not_applicable' : '3'])), comments: {} })
  assert.equal(payload.questionnaire_version, 3)
  assert.equal(payload.ratings.learning, 3)
  assert.equal(Object.hasOwn(payload.ratings, 'comfort'), false)
})

test('public camp details use API fees/theme without opening closed registration or inventing categories', () => {
  const options = { name: 'Configured edition', venue: 'Configured venue', general_information: { theme: 'Approved theme' }, registration_is_open: false,
    categories: [{ id: 1, name: 'Approved category', early_bird_fee_ngn: '4000.00', regular_fee_ngn: '5000.00' }] }
  const html = render(Info, { options, optionsState: 'ready' })
  for (const text of ['Approved category', '4,000', '5,000', 'Early Bird', 'Regular']) assert.ok(html.includes(text))
  const landing = render(Landing, { options, optionsState: 'ready' })
  assert.match(landing, /<h1 class="dic-theme">Approved theme<\/h1>/)
  assert.match(html, /disabled=""/)
  const noCategories = render(Info, { options: { ...options, registration_is_open: true, categories: [] }, optionsState: 'ready' })
  assert.doesNotMatch(noCategories, /Approved category|4,000|5,000|<table/)
  assert.match(noCategories, /disabled=""/)
  assert.match(html, /href="\/dic\/participant"/)
  const unavailable = render(Info, { options: null, optionsState: 'error' })
  assert.doesNotMatch(unavailable, /4,000|Approved category|The Outliers|Fazil/)
  assert.match(unavailable, /temporarily unavailable/)
})

test('unpublished editorial is not replaced with preview media in production rendering', () => {
  const html = render(Editorial)
  assert.match(html, /Loading approved camp media/)
  assert.doesNotMatch(html, /<video|<img|Local preview/)
})

test('anonymous staff probes and failed credentials reject without false session expiry; protected failures expire', async () => {
  const originalFetch = globalThis.fetch, originalWindow = globalThis.window
  const events = [], calls = []
  globalThis.window = { dispatchEvent: event => events.push(event.type) }
  globalThis.fetch = async (url, options) => {
    calls.push(options)
    return url.endsWith('/csrf/') ? Response.json({ csrfToken: 'synthetic-csrf' }) : Response.json({ detail: 'Authentication credentials were not provided.' }, { status: 401 })
  }
  try {
    await assert.rejects(getOperationsUser(), error => error.status === 401)
    await assert.rejects(signIn('synthetic', 'synthetic'), error => error.status === 401)
    assert.deepEqual(events, [])
    await assert.rejects(getOperationsData('/participants/'), error => error.status === 401)
    assert.deepEqual(events, ['operations-session-expired'])
    assert.ok(calls.every(options => !Object.hasOwn(options, 'notifySessionExpiry')))
  } finally { globalThis.fetch = originalFetch; globalThis.window = originalWindow }
})

test('current security boundary, private drafts and safe payment callbacks survive recovery', () => {
  const main = source('../main.jsx'), dic = source('../pages/DIC.jsx')
  assert.match(main, /<GlobalErrorBoundary><App/)
  for (const helper of ['privateDraft', 'registrationSubmission', 'paystackCheckoutUrl', 'preparePaymentReturn']) assert.ok(dic.includes(helper))
  const portal = source('../pages/ParticipantPortal.jsx')
  assert.match(portal, /access.invalidate\(\); setCard\(null\); setSelection\(value\)/)
  assert.match(portal, /assertAccess\(ticket\)/)
  assert.doesNotMatch(source('../components/dic/DigitalIDPresentation.jsx'), /<iframe|fetch\(|issue.*POST/)
  const ops = source('../pages/Operations.jsx')
  assert.match(ops, /user.can_access_campsite \? <AssistedRegistration/)
  assert.match(ops, /<Link className="ops-website-link" to="\/">Main website<\/Link>/)
})

test('all public pages render with preserved route components without backend effects', async () => {
  for (const name of ['Home', 'Programs', 'Events', 'Projects', 'Media', 'GetInvolved', 'Contact', 'FAQ', 'Donate']) {
    const Page = (await server.ssrLoadModule(`/src/pages/${name}.jsx`)).default
    const html = render(Page)
    assert.ok(html.length > 200, name)
    assert.doesNotMatch(html, /SYNTHETIC DIC Camp|leadership_e2e/)
  }
})
