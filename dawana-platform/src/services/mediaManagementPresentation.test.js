import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import fs from 'node:fs'

let vite, MediaManagement
before(async () => {
  vite = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  MediaManagement = (await vite.ssrLoadModule('/src/pages/MediaManagement.jsx')).default
})
after(async () => { await vite?.close() })

test('media workspace exposes all three existing restricted Django administration libraries', () => {
  const html = renderToStaticMarkup(createElement(MediaManagement))
  assert.match(html, /Media management/)
  for (const [model, title] of [['campphotograph','Photos'],['campvideo','Camp videos'],['lecturerecording','Lecture recordings']]) {
    assert.match(html, new RegExp(`/admin/dic/${model}/`))
    assert.ok(html.includes(title))
  }
  assert.equal((html.match(/class="ops-media-card"/g) || []).length, 3)
  assert.match(html, /publisher permission/)
  assert.match(html, /Storage activation remains under owner control/)
  assert.doesNotMatch(html, /<input[^>]*type="file"|Publish now|Activate storage/)
})

test('media management stacks at phone width and retains a compact header', () => {
  const css = fs.readFileSync(new URL('../pages/MediaManagement.css', import.meta.url), 'utf8')
  assert.match(css, /@media\(max-width:600px\)/)
  assert.match(css, /\.ops-media-grid \{ grid-template-columns:minmax\(0,1fr\);/)
  assert.match(css, /\.ops-app:has\(\.ops-media\) \.ops-topbar \{ display:flex; flex-wrap:nowrap;/)
})
