import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createHash } from 'node:crypto'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
let server, Experience, Content, Arena, Brand
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  const module = await server.ssrLoadModule('/src/components/dic/CamperExperience.jsx')
  Experience = module.default; Content = module.ExperienceContent; Arena = module.HouseArena
  Brand = (await server.ssrLoadModule('/src/components/dic/CamperBrand.jsx')).default
})
after(async () => { await server?.close() })
const participant = { registration_item_id: 1, name: 'Test Camper', category: 'Test category', eligibility: { eligible: false, code: 'registration_not_verified_paid' }, house_assignment: null, checked_in: false }
const order = { edition: 'Test DIC 2026', reference: 'booking-reference', status: 'submitted', payment_status: 'pending', participants: [participant] }
const data = { ready: true, total: 0, history: [], house: null, house_leaderboard: [], standings_ready: true, standings: [], page: 1, count: 0, page_size: 25 }
const render = (Component, props) => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Component, props)))
const content = (tab, extra = {}) => render(Content, { tab, participant, order, data, onNavigate() {}, onPage() {}, onRefresh() {}, onOpenID() {}, ...extra })

test('portal reuses the exact official public-site logo, with a valid local PNG', () => {
  const asset = fs.readFileSync(new URL('../../public/dawana-official-logo.png', import.meta.url))
  const original = fs.readFileSync(new URL('../../../backend/dic/static/dic/dawana-official-logo.img', import.meta.url))
  const metadata = JSON.parse(fs.readFileSync(new URL('../../../backend/dic/static/dic/dawana-official-logo.img.json', import.meta.url), 'utf8').replace(/^\uFEFF/, ''))
  assert.deepEqual(asset, original)
  assert.equal(createHash('sha256').update(asset).digest('hex').toUpperCase(), metadata.sha256)
  const publicHeader = fs.readFileSync(new URL('../components/layout/SiteChrome.jsx', import.meta.url), 'utf8')
  assert.match(publicHeader, /const logoSrc = '\/dawana-official-logo\.png'/)
  assert.doesNotMatch(publicHeader, /lh3\.googleusercontent\.com/)
  assert.equal(asset.subarray(0, 8).toString('hex'), '89504e470d0a1a0a')
  assert.ok(asset.readUInt32BE(16) > 0 && asset.readUInt32BE(20) > 0)
  const markup = render(Brand, {})
  assert.match(markup, /src="\/dawana-official-logo.png"/)
  assert.match(markup, /alt="Dawana Islamic Foundation official logo"/)
  assert.match(markup, /DIC 2026/)
  assert.match(markup, /Camper Portal/)
})

test('official branding is shared by authenticated header, login, OTP and handoff', () => {
  const markup = render(Experience, { orders: [order], expiresAt: '2026-12-23T12:30:00Z' })
  assert.match(markup, /<header class="cp-header">.*dawana-official-logo.png/s)
  const portal = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
  assert.match(portal, /!profile && <div className="participant-page-heading">.*<CamperBrand \/>/)
  const registration = fs.readFileSync(new URL('../pages/DIC.jsx', import.meta.url), 'utf8')
  assert.match(registration, /cp-portal-handoff-brand"><CamperBrand \/>/)
  const styles = fs.readFileSync(new URL('../components/dic/CamperBrand.css', import.meta.url), 'utf8')
  assert.match(styles, /object-fit:contain/)
  assert.match(styles, /background:#fffdf5/)
  assert.match(styles, /@media\(max-width:350px\)/)
  assert.doesNotMatch(styles, /object-fit:cover|overflow:\s*hidden/)
})

test('dedicated shell exposes five functional destinations and one selected camper', () => {
  const markup = render(Experience, { orders: [order], selection: '', expiresAt: '2026-12-23T12:30:00Z' })
  assert.match(markup, /aria-label="Camper navigation"/)
  for (const label of ['Home', 'My Day', 'Arena', 'Explore', 'Me']) assert.ok(markup.includes(label))
  assert.equal((markup.match(/aria-current="page"/g) || []).length, 1)
  assert.match(markup, /Loading verified camp points/)
  assert.doesNotMatch(markup, /Notifications|unread|sessionid|qr_code/)
})

test('home uses verified zero and explicit unassigned states without fictional activity', () => {
  const markup = content('home')
  assert.match(markup, /As-salāmu/)
  assert.match(markup, /Test Camper/)
  assert.match(markup, /<strong>0<\/strong>/)
  assert.match(markup, /Assignment coming soon/)
  for (const label of ['Activities', 'Meals', 'House Arena', 'My Digital ID', 'Discover', 'Feedback']) assert.ok(markup.includes(label))
  assert.match(markup, /Today’s programme/)
  assert.match(markup, /No participant houses are configured/)
})

test('points uses backend totals, original activity labels and reversal state', () => {
  const markup = content('points', { data: { ...data, total: 13, history: [{ id: 7, activity: 'Arrival before adhān', date: '2026-12-23', slot: 'fajr', house: 'Test House', points: 3, reversed: true }] } })
  assert.match(markup, /<strong class="cw-own-points">13<\/strong>/)
  assert.match(markup, /Arrival before adhān/)
  assert.match(markup, /<s>\+3<\/s>/)
  assert.match(markup, /Reversed · 0/)
})

test('scoring errors and pending schema do not masquerade as a zero score', () => {
  const failed = content('home', { data: null, error: 'Temporary scoring outage' })
  assert.match(failed, /Temporary scoring outage/)
  assert.match(failed, /Retry points/)
  assert.doesNotMatch(failed, /<strong>0<\/strong>/)
  const pending = content('points', { data: { ...data, ready: false, message: 'Scoring setup pending' } })
  assert.match(pending, /Scoring setup pending/)
  assert.doesNotMatch(pending, /<strong>0<\/strong>/)
})

test('unpaid profile shows navigable ID review status without an authorized ID action', () => {
  const markup = content('profile')
  assert.match(markup, /submitted/)
  assert.match(markup, /pending/)
  assert.match(markup, /Not checked in/)
  assert.match(markup, /Not yet assigned/)
  assert.match(markup, /Your ID needs a staff review/)
  assert.doesNotMatch(markup, /Open my Digital ID/)
  assert.match(markup, /Awaiting active ID/)
  assert.doesNotMatch(markup, /QR|<canvas|verification credential/)
})

test('eligible profile uses existing ID callback, and camper changes cannot retain old identity', () => {
  const eligible = { ...participant, name: 'First Camper', id: 'one', participant_number: 'DIC-ONE', eligibility: { eligible: true, code: 'verified_paid' }, issue: { status: 'current' }, house_assignment: { name: 'First House' } }
  const markup = content('profile', { participant: eligible })
  assert.match(markup, /Open my Digital ID/)
  assert.doesNotMatch(markup, /disabled=""/)
  const second = content('profile')
  assert.doesNotMatch(second, /First Camper|First House|DIC-ONE/)
})

test('house arena preserves server ranks, tied/negative scores and highlights only assigned house', () => {
  const markup = render(Arena, { house: 'House B', data: { standings_ready: true, standings: [{ house_id: 1, rank: 1, name: 'House A', net: 8 }, { house_id: 2, rank: 1, name: 'House B', net: 8 }, { house_id: 3, rank: 3, name: 'House C', net: -2 }] } })
  assert.equal((markup.match(/class="cp-rank">1</g) || []).length, 2)
  assert.equal((markup.match(/cp-own-house/g) || []).length, 1)
  assert.match(markup, />-2</)
})

test('camp screen offers real links and only supplied matching edition details', () => {
  const empty = content('camp')
  assert.match(empty, /href="\/dic#showcase-activities-title"/)
  assert.match(empty, /Feedback &amp; care/)
  assert.match(empty, /Camp announcements/)
  assert.doesNotMatch(empty, /23 Dec|Faisal/)
  const configured = content('camp', { camp: { camp_start_date: '2026-12-23', camp_end_date: '2027-01-01', venue: 'Configured venue' } })
  assert.match(configured, /Configured venue/)
  assert.match(configured, /23 Dec 2026/)
})

test('handoff prefills only UUID booking context; authentication and OTP remain required', () => {
  const portal = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
  const registration = fs.readFileSync(new URL('../pages/DIC.jsx', import.meta.url), 'utf8')
  assert.match(registration, /<PortalContinuation orderReference=\{flow.orderId\}/)
  assert.match(portal, /location.state\?\.bookingReference/)
  assert.match(portal, /\/auth\/verify\//)
  assert.match(portal, /codeExpiresAt/)
  assert.doesNotMatch(registration, /\/dic\/participant\?[^"']*(token|code)=/)
})

test('shell has safe-area space, no scrolling trap and disables generic site chrome on portal route', () => {
  const css = fs.readFileSync(new URL('../components/dic/CamperExperience.css', import.meta.url), 'utf8')
  assert.match(css, /safe-area-inset-bottom/)
  assert.match(css, /padding:10px 16px 110px/)
  assert.match(css, /prefers-reduced-motion:reduce/)
  assert.doesNotMatch(css, /overflow(?:-y)?:\s*(auto|scroll)|(?:^|[;{]\s*)height:\s*100(?:d|s)?vh/)
  const shell = fs.readFileSync(new URL('../components/layout/SiteChrome.jsx', import.meta.url), 'utf8')
  assert.match(shell, /<main className="cp-route">\{children\}<\/main>/)
})
