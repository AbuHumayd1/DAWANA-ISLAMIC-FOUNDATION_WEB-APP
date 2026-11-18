import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

test('browser tab icons use DAWANA identity, not starter Vite lightning', () => {
  const html = fs.readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
  const icon = fs.readFileSync(new URL('../../public/favicon.svg', import.meta.url), 'utf8')
  assert.match(html, /<link rel="icon" type="image\/svg\+xml" href="\/favicon\.svg\?v=20261118-dawana"/)
  assert.match(html, /<link rel="apple-touch-icon" href="\/dawana-official-logo\.png\?v=20261118-dawana"/)
  assert.match(icon, /DAWANA Islamic Foundation/)
  assert.match(icon, /#138451|#185d3d/)
  assert.doesNotMatch(icon, /#863bff|#7e14ff|vite|Vite|lightning/i)
  assert.equal(fs.existsSync(new URL('../assets/vite.svg', import.meta.url)), false)
})
