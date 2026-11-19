import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const jsx = readFileSync(new URL('../components/dic/DICEditorial.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../components/dic/DICLandingRefinements.css', import.meta.url), 'utf8')

test('official flyer retains public published image and offers full-size viewing', () => {
  assert.match(jsx, /resolveMediaUrl\(flyer\.image_url\)/)
  assert.match(jsx, /dialog\.current/)
  assert.match(jsx, /node\.showModal\(\)/)
  assert.match(jsx, /onCancel=\{event => \{ event\.preventDefault\(\); setOpen\(false\) \}\}/)
  assert.match(jsx, /event\.target === event\.currentTarget/)
  assert.match(jsx, /opener\?\.focus\(\)/)
  assert.match(jsx, /className="dic-flyer-viewer-image"/)
  assert.match(jsx, /Open full image/)
  assert.match(jsx, /rel="noopener noreferrer"/)
})
test('flyer lightbox is explicitly centred and large on desktop and mobile', () => {
  assert.match(css, /\.dic-flyer-viewer:modal\s*\{[^}]*position:fixed;[^}]*inset:0;[^}]*margin:auto;/)
  assert.match(css, /\.dic-flyer-viewer:not\(\[open\]\)\{display:none\}/)
  assert.match(css, /\.dic-flyer-viewer-image img\s*\{[^}]*max-width:100%;[^}]*max-height:calc/)
  assert.match(css, /\.dic-flyer-open img\{[^}]*max-height:600px/)
  assert.match(css, /@media\(max-width:700px\)/)
  assert.match(css, /\.dic-flyer-viewer:modal\{width:calc\(100vw - 20px\)/)
})
test('flyer section stays descriptive and action oriented without fabricated schedule details', () => {
  assert.match(jsx, /className="dic-flyer-info"/)
  assert.match(jsx, /className="dic-flyer-actions"/)
  assert.match(jsx, /disabled=\{!canRegister\}/)
  assert.doesNotMatch(jsx, /width="800" height="1100"/)
})
