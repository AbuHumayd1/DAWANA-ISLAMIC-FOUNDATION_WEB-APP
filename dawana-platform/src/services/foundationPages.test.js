import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'

let server, Contact, Donate
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Contact = (await server.ssrLoadModule('/src/pages/Contact.jsx')).default
  Donate = (await server.ssrLoadModule('/src/pages/Donate.jsx')).default
})
after(async () => { await server?.close() })

test('Contact page renders enquiry links and safe loading states without undefined helpers', () => {
  const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Contact)))
  assert.match(html, /Contact Us/)
  assert.match(html, /href="\/dic"/)
  assert.match(html, /Loading official contact channels/)
  assert.match(html, /Checking enquiry availability/)
  assert.doesNotMatch(html, /Your message has been sent/)
})
test('Donate page preserves branding and separates donations from registration', () => {
  const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Donate)))
  assert.match(html, /Support the Work of Dawana/)
  assert.match(html, /separate from DIC registration fees/)
  assert.match(html, /Checking donation availability/)
  assert.doesNotMatch(html, /href="https:\/\/checkout/)
})
