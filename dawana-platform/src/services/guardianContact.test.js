import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { requiresGuardianContact, validateGuardianContact } from './guardianContact.js'

let server, Fields
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Fields = (await server.ssrLoadModule('/src/components/dic/PrimaryRegistrantFields.jsx')).default
})
after(async () => { await server?.close() })

test('guardian requirement uses the camp date and the exact sixteenth birthday', () => {
  for (const [dob, required] of [['2010-12-24', true], ['2010-12-23', false], ['2009-12-23', false], ['2008-12-23', false], [null, false]]) {
    assert.equal(requiresGuardianContact([{ dob }]), required)
    if (required) assert.throws(() => validateGuardianContact([{ dob }], {}), /guardian phone/)
    else validateGuardianContact([{ dob }], {})
  }
  validateGuardianContact([{ dob: '2011-01-01' }], { phone: '+234 801 234 5678' })
})

test('changing the age immediately hides guardian wording without clearing saved contact', () => {
  const contact = { fullName: 'Saved Guardian', email: 'saved@example.test', phone: '+2348012345678' }
  const render = dob => renderToStaticMarkup(createElement(Fields, { participants: [{ dob }], contact, onChange() {} }))
  assert.match(render('2010-12-24'), /Parent or guardian name/)
  for (const dob of ['2010-12-23', '2009-12-23', '2000-01-01', null]) {
    const html = render(dob)
    assert.doesNotMatch(html, /Parent or guardian/)
    assert.match(html, /Booking phone \(optional\)/)
    assert.match(html, /Saved Guardian/)
  }
})

test('checkout displays the original email without requesting it again', () => {
  const html = renderToStaticMarkup(createElement(Fields, { readOnly: true,
    contact: { fullName: 'Owner', email: 'owner@example.test' }, onChange() {}, participants: [{ dob: '2011-01-01' }] }))
  assert.match(html, /owner@example.test/)
  assert.doesNotMatch(html, /type="email"|Parent or guardian name|Parent or guardian phone/)
})
