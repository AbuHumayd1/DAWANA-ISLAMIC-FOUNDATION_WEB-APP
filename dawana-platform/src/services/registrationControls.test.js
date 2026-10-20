import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

let server, Field, Select
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  const module = await server.ssrLoadModule('/src/components/dic/RegistrationField.jsx')
  Field = module.default
  Select = module.RegistrationSelect
})
after(async () => { await server?.close() })

test('select retains field values and native required validity behind a labelled combobox', () => {
  const html = renderToStaticMarkup(createElement(Select, {
    id: 'academicStatus', label: 'Academic Status', required: true,
    value: 'Secondary Student', options: ['Primary Student', 'Secondary Student'], onChange() {},
  }))
  assert.match(html, /name="academicStatus"/)
  assert.match(html, /required=""/)
  assert.match(html, /value="Secondary Student" selected=""/)
  assert.match(html, /role="combobox"/)
  assert.match(html, /aria-labelledby="academicStatus-label academicStatus-value"/)
  assert.match(html, /aria-expanded="false"/)
  assert.match(html, /role="listbox"/)
  assert.match(html, /inert=""/)
})

test('recovery options preserve unavailable channels without making them selectable', () => {
  const html = renderToStaticMarkup(createElement(Select, {
    id: 'recovery-channel', label: 'Verification method', value: 'email', onChange() {},
    options: [{ value: 'email', label: 'Email' }, { value: 'sms', label: 'SMS — unavailable', disabled: true }],
  }))
  assert.match(html, /value="sms" disabled=""/)
  assert.match(html, /aria-disabled="true"/)
  assert.match(html, /aria-selected="true"/)
})

test('date and measurement controls keep names, required fields and validation bounds', () => {
  const date = renderToStaticMarkup(createElement(Field, { label: 'Date of Birth', name: 'dob', type: 'date', value: '', max: '2026-10-20', onChange() {} }))
  assert.match(date, /for="dob"/)
  assert.match(date, /type="text"/)
  assert.match(date, /name="dob"/)
  assert.match(date, /aria-haspopup="dialog"/)
  assert.match(date, /autoComplete="bday"/i)
  assert.match(date, /max="2026-10-20"/)
  assert.match(date, /required=""/)
  const number = renderToStaticMarkup(createElement(Field, { label: 'Height', name: 'height', type: 'number', value: '175', min: '0.01', step: '0.01', unit: 'cm', onChange() {} }))
  assert.match(number, /name="height"/)
  assert.match(number, /min="0.01"/)
  assert.match(number, /step="0.01"/)
  assert.match(number, />cm</)
})
