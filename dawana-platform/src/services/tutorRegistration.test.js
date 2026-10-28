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
    assert.match(html, /Open my Digital ID/)
    assert.match(html, /Explore approved camp activities/)
    assert.doesNotMatch(html, /House assignment|House Arena|My Points|championship|Not yet assigned/)
  }
})

test('tutor uses the existing participant form without a selectable category or minor mode', () => {
  const html = render(Form, { tutor: true, initial: { fullName: 'Tutor', email: 'tutor@example.test', ageChoice: 'adult_private' },
    categories: [], options: {}, onBack() {}, onSave() {} })
  assert.match(html, /Height \(optional\)/)
  assert.match(html, /Weight \(optional\)/)
  assert.match(html, /Complete complimentary registration/)
  assert.doesNotMatch(html, /value="minor"|name="categoryId"|Continue to summary/)
})
