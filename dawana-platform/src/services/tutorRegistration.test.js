import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
let server, Content, Form
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Content = (await server.ssrLoadModule('/src/components/dic/CamperExperience.jsx')).ExperienceContent
  Form = (await server.ssrLoadModule('/src/pages/DIC.jsx')).ParticipantForm
})
after(async () => { await server?.close() })
const render = (component, props) => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component, props)))

test('tutor portal has ID and activities but no housing or competition sections', () => {
  for (const tab of ['home', 'profile', 'camp', 'houses', 'points']) {
    const html = render(Content, { tab, participant: { name: 'Tutor', id: 'enrollment', registration_basis: 'tutor',
      eligibility: { eligible: true, code: 'authorized_tutor' }, issue: { status: 'current' } },
    order: { edition: 'Synthetic DIC', reference: 'reference' }, onOpenID() {} })
    if (tab === 'home') assert.match(html, /My Digital ID/)
    if (['profile', 'houses', 'points'].includes(tab)) assert.match(html, /Open my Digital ID/)
    if (tab === 'camp') assert.match(html, /Explore approved camp activities/)
    assert.doesNotMatch(html, /House assignment|House Arena|My Points|championship|Not yet assigned/)
  }
})

test('tutor uses the existing participant form without a selectable category or minor mode', () => {
  const html = render(Form, { tutor: true, initial: { fullName: 'Tutor', email: 'tutor@example.test', ageChoice: 'adult_private' },
    categories: [], options: {}, onBack() {}, onSave() {} })
  assert.match(html, /Measurements/)
  assert.ok(html.includes('Optional \u2014 leave blank if unknown.'))
  for (const [name, label] of [['height', 'Height'], ['weight', 'Weight']]) {
    assert.ok(html.includes(`<label for="${name}">${label}</label>`))
    const input = html.match(new RegExp(`<input(?=[^>]*\\bname="${name}")[^>]*>`))
    assert.ok(input, `${label} input is present`)
    assert.doesNotMatch(input[0], /\brequired(?:\s|=|>)/)
  }
  assert.match(html, /Complete complimentary registration/)
  assert.doesNotMatch(html, /value="minor"|name="categoryId"|Continue to summary/)
})


test('tutor signup chooses username credentials and does not request an email code', async () => {
  const fs = await import('node:fs')
  const source = fs.readFileSync(new URL('../components/dic/TutorRegistration.jsx', import.meta.url), 'utf8')
  assert.ok(source.includes('registrationCredentialsPayload(credentials)'))
  assert.ok(source.includes('participant, portal_account'))
  assert.ok(source.includes('autoComplete="username"'))
  assert.equal(source.includes("request('verify'"), false)
  assert.equal(source.includes('Verify authorized email'), false)
})
