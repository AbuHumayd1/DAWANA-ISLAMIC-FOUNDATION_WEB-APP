import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
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


test('DOB wheel is portaled outside form stacking contexts for iPhone Safari', () => {
  const component = fs.readFileSync(new URL('../components/dic/DateField.jsx', import.meta.url), 'utf8')
  const styles = fs.readFileSync(new URL('../components/dic/DateField.css', import.meta.url), 'utf8')
  assert.match(component, /import \{ createPortal \} from 'react-dom'/)
  assert.match(component, /createPortal\(<div className="dic-wheel-backdrop"/)
  assert.match(component, /<\/section><\/div>, document\.body\)/)
  assert.match(styles, /body > \.dic-wheel-backdrop \{ position:fixed; inset:0; z-index:2147483000;/)
  assert.match(styles, /body > \.dic-wheel-backdrop > \.dic-wheel-dialog/)
  assert.match(component, /aria-modal="true"/)
  assert.match(component, /onPointerDown=\{e=>\{if\(e\.target===e\.currentTarget\) setOpen\(false\)\}\}/)
})


test('DOB wheel is kinetic, cylindrical and floating rather than a flat bottom sheet', () => {
  const component = fs.readFileSync(new URL('../components/dic/DateField.jsx', import.meta.url), 'utf8')
  const css = fs.readFileSync(new URL('../components/dic/DateField.css', import.meta.url), 'utf8')
  assert.match(component, /const ROW_HEIGHT=44/)
  assert.match(component, /role="listbox"/)
  assert.match(component, /onScroll=\{scrolling\}/)
  assert.match(component, /requestAnimationFrame\(paint\)/)
  assert.match(component, /scrollTo\(\{ top: index \* ROW_HEIGHT, behavior: 'auto' \}\)/)
  assert.match(component, /rotateX\(/)
  assert.match(component, /Math\.round\(scroller\.scrollTop \/ ROW_HEIGHT\)/)
  assert.match(component, /onKeyDown=\{keyDown\}/)
  assert.match(css, /height:220px; padding:88px 0; overflow-y:auto/)
  assert.match(css, /touch-action:pan-y/)
  assert.match(css, /-webkit-overflow-scrolling:touch/)
  assert.match(css, /perspective:430px/)
  assert.match(css, /backdrop-filter:blur\(14px\)/)
  assert.match(css, /align-items:center; justify-content:center; padding:14px/)
  assert.doesNotMatch(component, /onTouchMove=\{touchMove\}/)
})

test('Participant sign-in primary actions stay tappable while becoming sleek', () => {
  const css = fs.readFileSync(new URL('../pages/ParticipantPortal.css',import.meta.url), 'utf8')
  assert.match(css,/width:min\(100%,264px\); justify-self:center/)
  assert.match(css,/min-height:48px; border-radius:999px/)
  assert.match(css,/\.cp-route \.cp-auth \.cp-password-field button \{[^}]*min-height:44px/)
})

