import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { backendUrl } from './productionContract.js'

const publicFile = path => readFileSync(new URL(`../../public/${path}`, import.meta.url))

test('recovered local font faces and licenses match retained provenance hashes', () => {
  const source = JSON.parse(publicFile('fonts/sources.json'))
  const css = publicFile('fonts.css').toString()
  assert.equal(createHash('sha256').update(css).digest('hex'), source.local_css_sha256)
  for (const file of source.files) {
    assert.equal(createHash('sha256').update(publicFile(`fonts/${file.name}`)).digest('hex'), file.sha256, file.name)
    assert.match(file.url, /^https:\/\/(fonts\.gstatic\.com|raw\.githubusercontent\.com)\//)
  }
  for (const face of source.faces) assert.ok(css.includes(`/fonts/${face.local_name}`))
  assert.deepEqual(source.files.filter(file => file.name.endsWith('-OFL.txt')).map(file => file.name).sort(),
    ['amiri-OFL.txt', 'playfairdisplay-OFL.txt', 'plusjakartasans-OFL.txt', 'poppins-OFL.txt'])
  const index = readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
  assert.match(index, /href="\/fonts.css"/)
  assert.doesNotMatch(index, /fonts\.googleapis\.com|fonts\.gstatic\.com/)
})

test('public footer exposes distinct staff, participant and backend Admin destinations', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../../', import.meta.url)), configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  try {
    const { Footer } = await server.ssrLoadModule('/src/components/layout/SiteChrome.jsx')
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Footer)))
    assert.match(html, /href="\/dic\/operations"[^>]*>Staff Login/)
    assert.match(html, /href="\/admin\/">Django Admin Login/)
    assert.match(html, /href="\/dic\/participant"[^>]*>Participant portal/)
    assert.match(html, /src="\/dawana-official-logo.png"/)
    assert.equal(backendUrl('/admin/', 'https://api.example.test/api/v1'), 'https://api.example.test/admin/')
    assert.throws(() => backendUrl('/admin/', 'http://api.example.test/api/v1'))
  } finally { await server.close() }
})

test('recurring event badge retains its compact historical label without overflowing at mobile width', () => {
  const css = readFileSync(new URL('../App.css', import.meta.url), 'utf8')
  const badge = css.match(/\.event-badge strong\s*\{([^}]+)\}/)?.[1]
  assert.match(badge, /max-width:100%/)
  assert.match(badge, /font-size:0\.5625rem/)
  assert.match(badge, /white-space:nowrap/)
})
