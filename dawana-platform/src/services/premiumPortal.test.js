import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import { portalView, activeDestination, todayProgramme, campDayLabel, digitalIDState } from './premiumPortal.js'

let server, experience, home, accounts
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  experience = await server.ssrLoadModule('/src/components/dic/CamperExperience.jsx')
  home = await server.ssrLoadModule('/src/components/dic/CamperHome.jsx')
  accounts = await server.ssrLoadModule('/src/components/dic/PortalAccountAccess.jsx')
})
after(async () => { await server?.close() })
const render = (component, props, route = '/') => renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: [route] }, createElement(component, props)))
const p = { registration_item_id: 4, name: '<Camper>', category: 'Camper', eligibility: { eligible: true, code: 'verified_paid' }, issue: null }
const order = { edition: 'Test edition', reference: 'TEST-PRIVATE', status: 'confirmed', payment_status: 'paid', participants: [p] }
const schedule = { today: '2026-12-23', date: '2026-12-23', state: 'published', timezone: 'Africa/Lagos',
  dates: [{ date: '2026-12-23' }, { date: '2026-12-24' }],
  entries: [{ id: 3, time_label: '09:00', description: '<Approved activity>', location: 'Approved venue', instructions: 'Bring your notebook', certainty: 'proposed' }] }

test('legacy bookmarks resolve to real destinations with one active primary entry', () => {
  for (const [old, next] of [['profile','me'], ['timetables','day'], ['houses','arena'], ['points','arena'], ['camp','explore']]) assert.equal(portalView(old), next)
  assert.equal(portalView('untrusted'), 'home')
  for (const value of ['constructor', '__proto__', 'toString', null]) assert.equal(portalView(value), 'home')
  assert.equal(activeDestination('feedback'), 'explore')
  assert.equal(activeDestination('digital-id'), 'me')
})

test('home never relabels a future published programme as today or exposes drafts', () => {
  assert.equal(todayProgramme(schedule).length, 1)
  assert.deepEqual(todayProgramme({ ...schedule, date: '2026-12-24' }), [])
  assert.deepEqual(todayProgramme({ ...schedule, state: 'unpublished' }), [])
  const future = render(home.ProgrammePreview, { data: { ...schedule, date: '2026-12-24' } })
  assert.match(future, /No activities are published for today/)
  assert.doesNotMatch(future, /Approved activity/)
})

test('programme preview preserves approved labels, context, escaping and current markers', () => {
  const html = render(home.ProgrammePreview, { data: { ...schedule, current: 3 } })
  for (const label of ['09:00', '&lt;Approved activity&gt;', 'Approved venue', 'Bring your notebook', 'Proposed', 'Happening now']) assert.ok(html.includes(label))
  assert.doesNotMatch(html, /<Approved activity>/)
})

test('camp day follows backend Lagos date and configured boundaries, not browser clock', () => {
  assert.equal(campDayLabel(schedule), 'Camp day 1')
  assert.equal(campDayLabel({ ...schedule, today: '2026-12-24' }), 'Camp day 2')
  assert.equal(campDayLabel({ ...schedule, today: '2026-12-22' }), 'Camp begins soon')
  assert.equal(campDayLabel({ ...schedule, today: '2026-12-25' }), 'Camp has concluded')
  assert.equal(campDayLabel(null), 'Camp day pending')
})

test('home has six navigable tiles and no security, booking reference or disabled ID control', () => {
  const html = render(experience.ExperienceContent, { tab: 'home', participant: p, order, onNavigate() {} })
  assert.equal((html.match(/class="cp-feature-tile /g) || []).length, 6)
  assert.doesNotMatch(html, /TEST-PRIVATE|Sign-in settings|Account &amp; security|disabled=""/)
  assert.match(html, /&lt;Camper&gt;/)
})

test('account settings render exclusively in Me, including legacy profile bookmarks', () => {
  const marker = createElement('div', null, 'Security settings sentinel')
  for (const tab of ['home','day','arena','explore','feedback','announcements','digital-id']) {
    const html = render(experience.ExperienceContent, { tab, participant: p, order, accountSettings: marker })
    assert.doesNotMatch(html, /Security settings sentinel/)
  }
  const me = render(experience.default, { orders: [order], accountSettings: marker, expiresAt: '2026-12-23T12:00:00Z' }, '/dic/participant?view=me')
  assert.match(me, /<details class="cw-account-drawer"><summary/)
  assert.match(me, /Security settings sentinel/)
  assert.doesNotMatch(me, /<details class="cw-account-drawer" open/)
})

test('ID authorization requires enrollment, eligibility and current issuance together', () => {
  assert.equal(digitalIDState(p).available, false)
  assert.equal(digitalIDState({ ...p, id: 9, issue: { status: 'current' } }).available, true)
  for (const changed of [{ issue: { status: 'current' } }, { id: 9, issue: { status: 'revoked' } }, { id: 9, issue: { status: 'current' }, eligibility: { eligible: false } }]) {
    assert.equal(digitalIDState({ ...p, ...changed }).available, false)
  }
  const pending = render(experience.DigitalIDStatus, { participant: p })
  assert.match(pending, /when issuance is complete/)
  assert.doesNotMatch(pending, /Staff issuance required|officer still needs/)
  assert.doesNotMatch(pending, /Open my Digital ID|<canvas|<img/)
})

test('automatic preparation status is visible without turning pending work into an issued ID', () => {
  const held = { ...p, fulfillment: { state: 'held', message: 'The DIC team needs to review your house or Digital ID preparation.' } }
  assert.equal(digitalIDState(held).available, false)
  assert.equal(digitalIDState(held).detail, held.fulfillment.message)
  assert.equal(digitalIDState({ ...held, id: 9, issue: { status: 'current' } }).available, true)
  const expired = { ...p, id: 9, issue: { status: 'expired' }, fulfillment: { state: 'completed', message: 'Preparation is complete.' } }
  assert.equal(digitalIDState(expired).available, false)
  assert.doesNotMatch(digitalIDState(expired).detail, /Preparation is complete/)
})

test('feedback hub keeps daily, complaint submission, complaint history and final evaluation', () => {
  const html = render(experience.ExperienceContent, { tab: 'feedback', participant: p, order })
  for (const channel of ['daily', 'welfare', 'history', 'final']) assert.ok(html.includes(`/dic/feedback?channel=${channel}`))
})

test('eligible OTP recovery controls appear only when delivery is configured', () => {
  const props = { capabilities: { accounts: { enabled: true } } }
  const disabled = render(accounts.PortalCredentialLogin, props)
  assert.doesNotMatch(disabled, />Forgot Password<|>First-Time Account Setup</)
  assert.doesNotMatch(disabled, /Resend email verification link/)
  assert.match(disabled, /Recover username access without email/)
  const configured = render(accounts.PortalCredentialLogin, { ...props, recoveryAvailable: true })
  assert.match(configured, />Forgot Password</)
  assert.match(configured, />First-Time Account Setup</)
  assert.doesNotMatch(configured, /No email activation is required/)
})

test('food deep link and participant switch keep the real timetable item scope', () => {
  const html = render(experience.default, { orders: [order], expiresAt: '2026-12-23T12:00:00Z' }, '/dic/participant?view=day&type=food')
  assert.match(html, /aria-haspopup="listbox"/)
  assert.match(html, />Food Timetable<\/span>/)
  assert.match(html, /aria-current="page"[^>]*>.*My Day/s)
  const source = fs.readFileSync(new URL('../components/dic/CamperExperience.jsx', import.meta.url), 'utf8')
  assert.match(source, /key=\{selected.key\}/)
  assert.match(source, /focus\(\{ preventScroll: true \}\)/)
  assert.match(source, /state.onPage\?\.\(1\)/)
})

test('pastel text contrast and main green identity meet the design contract', () => {
  const css = fs.readFileSync(new URL('../components/dic/PremiumCamperPortal.css', import.meta.url), 'utf8')
  assert.match(css, /var\(--brand-deep\),var\(--brand-solid\)/)
  const rgb = hex => hex.match(/\w\w/g).map(v => parseInt(v,16)/255).map(v => v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4)
  const lum = hex => rgb(hex).reduce((sum,v,i) => sum + v * [.2126,.7152,.0722][i],0)
  for (const bg of ['e1f1e5','ffedcf','eee7fb','dfeef9','fbe4dc','f8efc9']) {
    for (const fg of ['092f23','42564a']) assert.ok((lum(bg)+.05)/(lum(fg)+.05) >= 4.5)
  }
  assert.match(css, /prefers-reduced-motion:reduce/)
  assert.match(css, /cp-skip-link:focus/)
  assert.doesNotMatch(css, /overflow-x:\s*hidden/)
})
