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
const lecturer = { id: 1, name: '<Synthetic lecturer>', image_url: '/synthetic.jpg', alt_text: 'Synthetic flyer', edition: { name: 'Synthetic edition' }, biography: 'Synthetic bio', topic: 'Synthetic topic', confirmed: false }

test('lecturer cards display the original full flyer without verification chatter or duplicate profile text', () => {
  for (const confirmed of [false, undefined, 'true', true]) {
    const html = renderToStaticMarkup(createElement(LecturerCard, { lecturer: { ...lecturer, confirmed } }))
    assert.match(html, /<img /)
    assert.match(html, /loading="lazy"/)
    assert.match(html, /Synthetic flyer/)
    assert.doesNotMatch(html, /Participation (confirmed|awaiting confirmation)/)
    assert.doesNotMatch(html, /topic awaiting verification/)
    assert.doesNotMatch(html, /Synthetic bio|Synthetic topic|Synthetic edition|Featured lecturer/)
    assert.match(html, /&lt;Synthetic lecturer&gt;/)
  }
})

test('historical flyers use the identical compact visual treatment without archive status notices', () => {
  const html = renderToStaticMarkup(createElement(LecturerCard, { lecturer, historical: true }))
  assert.match(html, /showcase-flyer/)
  assert.doesNotMatch(html, /verification|status|Confirmed|approved/i)
})
