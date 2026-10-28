import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { ageOnDate, privacyPayload, privacySummary } from './registrationPrivacy.js'
import { estimateRegistrationTotal } from './registrationPricing.js'

const today = '2026-10-26'
test('minor/adult disclosure and eighteenth birthday boundaries', () => {
  assert.equal(privacyPayload({ ageChoice: 'minor', dob: '2010-01-01' }, today).date_of_birth, '2010-01-01')
  assert.throws(() => privacyPayload({ ageChoice: 'minor' }, today))
  assert.equal(privacyPayload({ ageChoice: 'adult_dob', dob: '2008-10-26' }, today).age_declaration, 'adult')
  assert.throws(() => privacyPayload({ ageChoice: 'adult_dob', dob: '2008-10-27' }, today))
  assert.throws(() => privacyPayload({ ageChoice: 'minor', dob: '2000-01-01' }, today))
  assert.throws(() => privacyPayload({ ageChoice: 'minor', dob: '2027-01-01' }, today))
  assert.equal(ageOnDate('2026-02-31', today), null)
})
test('adult withholding never sends a stale exact DOB or invented date', () => {
  const result = privacyPayload({ ageChoice: 'adult_private', dob: '2000-01-01' }, today)
  assert.deepEqual(result, { age_declaration: 'adult', date_of_birth: null, height_cm: null, weight_kg: null })
  assert.match(privacySummary({ ageChoice: 'adult_private' }), /exact DOB not disclosed/)
  assert.throws(() => privacyPayload({}, today))
})
test('height/weight combinations preserve null and precise supplied values', () => {
  for (const [height, weight] of [['170.01', '60.01'], ['170.01', ''], ['', '60.01'], ['', '']]) {
    const result = privacyPayload({ ageChoice: 'adult_private', height, weight }, today)
    assert.equal(result.height_cm, height || null); assert.equal(result.weight_kg, weight || null)
  }
  for (const invalid of ['0', '-1', 'NaN', 'Infinity', '1.234', '123456789']) {
    assert.throws(() => privacyPayload({ ageChoice: 'adult_private', height: invalid }, today))
    assert.throws(() => privacyPayload({ ageChoice: 'adult_private', weight: invalid }, today))
  }
})
test('legacy exact-DOB drafts and multi-camper category prices remain compatible', () => {
  assert.equal(privacyPayload({ dob: '2000-01-01', height: '170', weight: '60' }, today).age_declaration, 'exact')
  const participants = [{ categoryId: '1', ageChoice: 'minor', dob: '2010-01-01' }, { categoryId: '1', ageChoice: 'adult_private' }]
  assert.equal(estimateRegistrationTotal(participants, [{ id: 1, current_fee_ngn: '12500.25' }]), 25000.50)
  assert.equal(participants.map(person => privacyPayload(person, today)).length, 2)
})

let server, Age, Measurements
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  const fields = await server.ssrLoadModule('/src/components/dic/RegistrationPrivacyFields.jsx')
  Age = fields.AgeDisclosureFields; Measurements = fields.OptionalMeasurements
})
after(async () => { await server?.close() })
test('adult privacy choice removes DOB input; minors retain required DOB', () => {
  const render = participant => renderToStaticMarkup(createElement(Age, { participant, today, onChange() {} }))
  const adult = render({ ageChoice: 'adult_private', dob: '' })
  assert.doesNotMatch(adult, /name="dob"/)
  assert.match(adult, /confirm that this camper is aged 18 or older/)
  for (const choice of ['minor', 'adult_dob']) {
    const html = render({ ageChoice: choice, dob: '' })
    assert.match(html, /name="dob"/); assert.match(html, /required/)
  }
})
test('measurements render requested labels and help without required attributes', () => {
  const html = renderToStaticMarkup(createElement(Measurements, { participant: { height: '', weight: '' }, onChange() {} }))
  assert.match(html, /Height \(optional\)/); assert.match(html, /Weight \(optional\)/)
  assert.ok(html.includes("If you don&#x27;t know your height or weight, you may leave these fields blank."))
  assert.doesNotMatch(html, /required=/)
})
