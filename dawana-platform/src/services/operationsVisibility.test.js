import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
let server, Tabs
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Tabs = (await server.ssrLoadModule('/src/components/operations/RegistrationTabs.jsx')).default
})
after(async () => { await server?.close() })
for (const view of ['active', 'all', 'archived', 'trash']) {
  test(`registration tabs select ${view}, retain payment filters and reset pagination`, () => {
    const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: [`/dic/operations/registrations?archive=${view}&payment_status=paid&page=3`] }, createElement(Tabs, { canRestore: true })))
    const links = [...html.matchAll(/<a\b([^>]+)>(.*?)<\/a>/g)]
    assert.equal(links.length, 4)
    assert.equal(links.filter(([, attrs]) => attrs.includes('aria-current="page"')).length, 1)
    assert.ok(links.every(([, attrs]) => attrs.includes('payment_status=paid') && !attrs.includes('page=3')))
    assert.match(html, /aria-label="Registration records"/)
    const selected = links.find(([, attrs]) => attrs.includes('aria-current="page"'))
    assert.ok(view === 'active' ? !selected[1].includes('archive=') : selected[1].includes(`archive=${view}`))
  })
}
test('default active selection and permission-gated Trash retain native links', () => {
  const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/dic/operations/registrations'] }, createElement(Tabs)))
  assert.equal((html.match(/class="ops-registration-tab"/g) || []).length, 3)
  assert.doesNotMatch(html, /archive=trash/)
  assert.match(html, /aria-current="page"[^>]*href="\/dic\/operations\/registrations"/)
})
