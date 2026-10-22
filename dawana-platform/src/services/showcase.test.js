import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

let server, LecturerCard
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  LecturerCard = (await server.ssrLoadModule('/src/components/dic/CampShowcase.jsx')).LecturerCard
})
after(async () => { await server?.close() })
const lecturer = { id: 1, name: '<Synthetic lecturer>', image_url: '/synthetic.jpg', alt_text: 'Synthetic portrait', edition: { name: 'Synthetic edition' }, biography: 'Synthetic bio', topic: 'Synthetic topic', confirmed: false }
test('upcoming confirmation must be an explicit boolean and content is escaped', () => {
  for (const confirmed of [false, undefined, 'true']) {
    const html = renderToStaticMarkup(createElement(LecturerCard, { lecturer: { ...lecturer, confirmed } }))
    assert.match(html, /Participation awaiting confirmation/)
    assert.doesNotMatch(html, /Participation confirmed/)
    assert.match(html, /&lt;Synthetic lecturer&gt;/)
    assert.match(html, /loading="lazy"/)
  }
  assert.match(renderToStaticMarkup(createElement(LecturerCard, { lecturer: { ...lecturer, confirmed: true } })), /Participation confirmed/)
})
test('historical lecture topics remain hidden until verified', () => {
  const html = renderToStaticMarkup(createElement(LecturerCard, { lecturer, historical: true }))
  assert.doesNotMatch(html, /Synthetic topic/)
  assert.match(html, /topic awaiting verification/)
  assert.match(renderToStaticMarkup(createElement(LecturerCard, { lecturer: { ...lecturer, confirmed: true }, historical: true })), /Verified lecture topic/)
})
