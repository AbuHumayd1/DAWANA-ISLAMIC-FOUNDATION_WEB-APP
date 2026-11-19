import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('../pages/MediaStudio.css', import.meta.url), 'utf8')
const markup = readFileSync(new URL('../pages/MediaStudio.jsx', import.meta.url), 'utf8')

test('Media Studio top navigation stays visible while workspace scrolls', () => {
  const header = source.match(/\.studio-top\{([^}]*)\}/)?.[1]
  assert.ok(header, 'expected Media Studio header styles')
  assert.match(header, /position:sticky/)
  assert.match(header, /top:0/)
  assert.match(header, /z-index:90/)
  assert.match(markup, /<header className="studio-top">/)
  assert.match(source, /\.studio-popnav\{[^}]*position:absolute/)
  assert.match(source, /\.studio-menu-backdrop\{position:fixed/)
  assert.match(source, /\.studio-preview-overlay\{position:fixed;inset:0;z-index:1000/)
})
