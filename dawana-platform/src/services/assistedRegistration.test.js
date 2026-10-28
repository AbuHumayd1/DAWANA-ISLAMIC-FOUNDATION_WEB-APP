import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { preparationPayload, assistedBookingPayload } from './assistedRegistration.js'
import { visibleOperationsNavigation } from './operationsNavigation.js'

const values = { category_id: '2', full_name: 'Synthetic camper', address: 'Synthetic address', phone: '08012345678',
  email: 'camper@example.test', date_of_birth: '2000-01-01', sex: 'Male', height_cm: '170.01', weight_kg: '70.01',
  academic_status: 'Tertiary Student', occupation: 'None', marital_status: 'None', payer_name: 'Synthetic payer',
  payer_email: 'payer@example.test', payer_phone: '' }

test('preparation preserves mandatory DOB and decimal strings without payment/ownership overrides', () => {
  const result = preparationPayload({ ...values, payment_status: 'paid', actor: 'fake', access_token: 'fake' })
  assert.equal(result.registration.participants[0].date_of_birth, values.date_of_birth)
  assert.equal(result.registration.participants[0].height_cm, '170.01')
  assert.equal(result.registration.participants[0].category_id, 2)
  assert.equal(JSON.stringify(result).includes('fake'), false)
  assert.deepEqual(preparationPayload(values), preparationPayload(values))
  assert.equal(result.registration.primary_registrant.email, 'payer@example.test')
})
test('missing camper details, category and payer ownership contact are rejected', () => {
  for (const field of ['date_of_birth', 'height_cm', 'academic_status', 'payer_name', 'category_id']) assert.throws(() => preparationPayload({ ...values, [field]: '' }))
  assert.throws(() => preparationPayload({ ...values, payer_email: '', payer_phone: '' }))
})
test('assisted multi-camper submission keeps one request reference and whitelists every camper', () => {
  const data = new FormData()
  for (const [key, value] of Object.entries(values)) data.append(key, value)
  for (const [key, value] of Object.entries(values)) if (!key.startsWith('payer_')) data.append(key, key === 'full_name' ? 'Second camper' : value)
  data.append('payment_status', 'paid')
  const payload = assistedBookingPayload(data, 'fixed-request-reference')
  assert.equal(payload.registration.participants.length, 2)
  assert.equal(payload.registration.participants[1].full_name, 'Second camper')
  assert.equal(payload.request_id, 'fixed-request-reference')
  assert.equal(JSON.stringify(payload).includes('paid'), false)
  assert.deepEqual(assistedBookingPayload(data, 'fixed-request-reference'), payload)
})
test('preparation navigation is removed for all staff capabilities', () => {
  const entries = flag => visibleOperationsNavigation({ can_access_campsite: flag, permissions: {} })
  assert.equal(entries(false).some(entry => entry.to.endsWith('/assisted-registration')), false)
  assert.equal(entries(true).some(entry => entry.to.endsWith('/assisted-registration')), false)
})

let server, Form, Guide
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  const page = await server.ssrLoadModule('/src/pages/AssistedRegistration.jsx')
  Form = page.AssistedPreparationForm
  const { MemoryRouter } = await import('react-router-dom')
  Guide = props => createElement(MemoryRouter, null, createElement(page.PayerHandoffGuide, props))
})
after(async () => { await server?.close() })
test('form explicitly checks details only and never offers register, pay or staff activation', () => {
  const html = renderToStaticMarkup(createElement(Form, { categories: [{ id: 2, name: 'Existing category' }] }))
  for (const name of ['date_of_birth', 'height_cm', 'weight_kg', 'email', 'phone', 'category_id']) assert.match(html, new RegExp(`name="${name}"[^>]*required=""|required=""[^>]*name="${name}"`))
  assert.match(html, /no booking created/)
  assert.match(html, /Check details only/)
  assert.match(html, /Clear private details/)
  assert.match(html, /autoComplete="off"/)
  assert.doesNotMatch(html, /Mark paid|Start payment|Issue QR/)
})
test('payer handoff uses existing public/recovery paths and distinguishes unconfigured delivery from pending status', () => {
  const render = props => renderToStaticMarkup(createElement(Guide, props))
  const html = render({ channels: [{ id: 'email', label: 'Email', available: true }] })
  assert.match(html, /href="\/dic\/register"/); assert.match(html, /href="\/dic\/register\/recover"/)
  assert.match(html, /payer’s own device/); assert.match(html, /Email/)
  assert.match(render({ channels: [] }), /No recovery delivery channel/)
  assert.match(render({}), /has not loaded yet/)
  assert.match(html, /Staff-created bookings are not enabled/)
})
test('creation controls require explicit server capability; uncertain requests lock editing', () => {
  const props = { categories: [{ id: 2, name: 'Existing category' }], canCreate: true }
  const html = renderToStaticMarkup(createElement(Form, props))
  assert.match(html, /Confirm and create booking/)
  assert.match(html, /Add another camper/)
  assert.doesNotMatch(html, /Mark paid|Start payment|Issue QR/)
  const locked = renderToStaticMarkup(createElement(Form, { ...props, locked: true }))
  assert.match(locked, /Retry same booking request/)
  assert.match(locked, /fieldset disabled/)
})
