import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const home = readFileSync(new URL('../pages/Home.jsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../pages/HomeMobileCards.css', import.meta.url), 'utf8')

test('six Foundation mandate cards remain intact, without decorative stars', () => {
  assert.match(home, /Six foundational areas of intervention/)
  assert.match(home, /What We Do/)
  assert.match(home, /areas\.map/)
  assert.doesNotMatch(home, /className="area-icon"/)
  assert.match(styles, /\.home-page #what-we-do \.area-card/)
  assert.match(styles, /\.home-page #what-we-do \.section-heading>p/)
  assert.match(styles, /@media\(max-width:600px\)/)
})

test('homepage monthly event uses text and existing recurrence tag, not squeezed badge', () => {
  assert.match(home, /Monthly Da&apos;wah Seminar/)
  assert.match(home, /Recurring Da&apos;wah Activity/)
  assert.doesNotMatch(home, /className="event-badge"/)
  assert.match(styles, /\.home-page #events \.event-empty/)
})
