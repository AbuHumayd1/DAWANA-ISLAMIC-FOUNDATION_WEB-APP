import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('Support Dawana uses dedicated scoped mobile-first typography and card presentation', () => {
  const jsx = source('../pages/Donate.jsx')
  const css = source('../pages/Donate.css')
  assert.match(jsx, /import '\.\/Donate\.css'/)
  assert.match(jsx, /<PageHero/)
  assert.match(jsx, /donate-support-grid/)
  assert.match(jsx, /donate-support-number/)
  assert.match(css, /\.donate-page \.public-hero h1/)
  assert.match(css, /font-family:var\(--donate-serif\)/)
  assert.match(css, /\.donate-support-grid article/)
  assert.match(css, /\.donate-details-card/)
  assert.match(css, /\.donate-contact-cta/)
  assert.match(css, /@media\(max-width:700px\)/)
  assert.match(css, /grid-template-columns:minmax\(0,1fr\)/)
  assert.match(css, /--donate-ink:var\(--heading\)/)
  assert.match(css, /prefers-reduced-motion/)
})

test('Donation remains backend-gated and copy does not invite unavailable payments', () => {
  const details = source('../components/foundation/FoundationExperience.jsx')
  assert.match(details, /options\?\.donations_enabled/)
  assert.match(details, /!options\.donations_enabled/)
  assert.match(details, /Online donations are not available yet/)
  assert.match(details, /collectionAvailable &&/)
  assert.match(details, /safeDonationCheckout\(payment\.authorization_url\)/)
  assert.doesNotMatch(details, /Donation collection is awaiting approved configuration/)
})
