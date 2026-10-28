import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { scanToken, scanPath, movementPath, stopCamera } from './camperMovement.js'

const token = 'A'.repeat(43)
test('scanner accepts existing raw token and QR fragment URL without navigating to its host', () => {
  assert.equal(scanToken(token), token)
  assert.equal(scanToken(`https://camp.example.test/api/v1/dic/ids/verify/#${token}`), token)
  assert.equal(scanToken(`http://127.0.0.1:8000/api/v1/dic/ids/verify/#${token}`), token)
})
test('invalid QR and query credentials are rejected without echoing the scanned value', () => {
  for (const value of ['private-invalid-value', 'A'.repeat(42), 'A'.repeat(44),
    `https://camp.test/wrong/#${token}`, `javascript:${token}`,
    `https://user:password@camp.test/api/v1/dic/ids/verify/#${token}`,
    `https://camp.test/api/v1/dic/ids/verify/?token=${token}`]) {
    assert.throws(() => scanToken(value), error => !error.message.includes(value))
  }
})
test('operational paths keep tokens out of URLs and require a valid edition', () => {
  assert.equal(scanPath(2), '/scan/?edition=2')
  const url = movementPath(2, 'person&other=value')
  assert.equal(new URL(`https://camp.test${url}`).searchParams.get('participant_id'), 'person&other=value')
  for (const edition of ['', '0', '../', 'a&b']) {
    assert.throws(() => scanPath(edition)); assert.throws(() => movementPath(edition, 'person'))
  }
})
test('camera cleanup stops every media track and accepts no active stream', () => {
  let stopped = 0
  stopCamera({ getTracks: () => [{ stop() { stopped++ } }, { stop() { stopped++ } }] })
  assert.equal(stopped, 2); stopCamera(null)
})

let server, Scanner, Results
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Scanner = (await server.ssrLoadModule('/src/components/operations/CamperScanner.jsx')).default
  Results = (await server.ssrLoadModule('/src/pages/CampCheckIn.jsx')).CheckInResults
})
after(async () => { await server?.close() })
test('scanner initially shows a stopped camera, explicit start and manual fallback without embedding secrets', () => {
  const html = renderToStaticMarkup(createElement(Scanner, { edition: 1, user: { permissions: {} } }))
  assert.match(html, /Start camera/); assert.match(html, /Stop camera/)
  assert.match(html, /Camera stopped/); assert.match(html, /Paste camper QR link or token/)
  assert.match(html, /Scanning only previews an ID/); assert.doesNotMatch(html, /autoplay|Confirm departure|Confirm return/)
})
test('manual movement history entry is visible only with movement-view authority', () => {
  const props = { rows: [{ participant_id: 'p', name: 'Synthetic', registration_number: 'TEST', participant_number: 'TEST',
    registration_status: 'confirmed', payment_status: 'paid', eligibility: { eligible: true, label: 'Eligible' } }], canCheckIn: false }
  const render = extra => renderToStaticMarkup(createElement(Results, { ...props, ...extra }))
  assert.doesNotMatch(render({}), /Movement history \/ record/)
  assert.match(render({ canViewMovements: true }), /Movement history \/ record/)
})
