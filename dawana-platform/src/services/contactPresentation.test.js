import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const foundation = readFileSync(new URL('../components/foundation/FoundationExperience.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../pages/ContactCards.css', import.meta.url), 'utf8')
const contact = foundation.slice(foundation.indexOf('export function FoundationContactForm()'),foundation.indexOf('function savedDonation()'))
test('Public contact page hides disabled enquiry feature and internal operational messages',()=>{
  assert.match(contact,/if \(!data\?\.contact_enabled\) return null/)
  assert.match(contact,/Have a question about our programmes, events or partnerships\?/)
  assert.doesNotMatch(contact,/camper welfare reporting|awaiting activation|Checking enquiry availability/)
  assert.match(contact,/<form className="contact-form"/)
  assert.match(contact,/foundationRequest\('\/contact\/'/)
})
test('Responsive public contact typography stays scoped to Contact',()=>{
  assert.match(css,/\.contact-page \.contact-main > \.container:has/)
  assert.match(css,/\.contact-page \.contact-form-panel > h2/)
  assert.match(css,/\.contact-page \.contact-enquiry-section \.contact-section-heading h2/)
  assert.match(css,/@media\(max-width:620px\)/)
})
