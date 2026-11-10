import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import crypto from 'node:crypto'

test('Operations reuses the approved local official logo under the existing self-only CSP', () => {
  const operations = fs.readFileSync(new URL('../pages/Operations.jsx', import.meta.url), 'utf8')
  assert.match(operations, /src="\/dawana-official-logo\.png" alt="Dawana Islamic Foundation"/)
  assert.doesNotMatch(operations, /lh3\.googleusercontent\.com/)
  const bytes = fs.readFileSync(new URL('../../public/dawana-official-logo.png', import.meta.url))
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), '3451550906402bd06027710b2781ac51f93e252b62a0006e7e54606cbcb374f0')
})
