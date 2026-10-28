import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import fs from 'node:fs'
import { activityScoringPath, camperScoringPath, campToday, activityPayload, participationPreview } from './activityScoring.js'

let server, Panels
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  Panels = (await server.ssrLoadModule('/src/components/dic/CamperScores.jsx')).CamperScorePanels
})
after(async () => { await server?.close() })
const members = [{ id: 'one', house: 1 }, { id: 'two', house: 1 }, { id: 'foreign', house: 2 }]
const houses = [{ id: 1, name: 'House One' }, { id: 2, name: 'House Two' }]
const values = { date: '2026-12-20', participant: 'one', house: '1', slot: 'fajr', note: 'Verified', verified: true, attendees: ['one', 'two', 'foreign'], exemptions: { two: 'Approved exemption' }, marks: {} }

test('request paths scope the camper through an item, without arbitrary house access', () => {
  assert.equal(activityScoringPath(1), '/scoring/activities/?edition=1')
  assert.equal(camperScoringPath(4, 2), '/scoring/?item=4&page=2')
  for (const item of ['1&house=2', '', -1]) assert.throws(() => camperScoringPath(item))
  assert.throws(() => camperScoringPath(1, 0))
  assert.equal(campToday(new Date('2026-10-25T23:30:00Z')), '2026-10-26')
})

test('individual payload sends verification without client points or a chosen house', () => {
  const payload = activityPayload(values, { code: 'SAL01', kind: 'individual' }, members, houses)
  assert.equal(payload.participant, 'one')
  assert.equal(payload.slot, 'fajr')
  assert.equal(payload.verified, true)
  assert.equal('points' in payload, false)
  assert.equal('house' in payload, false)
  assert.throws(() => activityPayload({ ...values, verified: false }, { code: 'SAL01' }, members, houses))
})

test('collective payload separates exemptions and excludes foreign house participants', () => {
  const payload = activityPayload(values, { code: 'HSP01', kind: 'collective', mode: 'participation' }, members, houses)
  assert.deepEqual(payload.attendees, ['one'])
  assert.deepEqual(payload.exemptions, [{ participant: 'two', reason: 'Approved exemption' }])
  assert.equal('participant' in payload, false)
  assert.equal('points' in payload, false)
  assert.deepEqual(participationPreview(members.slice(0, 2), values.attendees, values.exemptions), { numerator: 1, denominator: 1, percentage: 100 })
  assert.equal(participationPreview([], [], {}).percentage, null)
})

test('prayer target is derived by the server and official marks remain separate', () => {
  const payload = activityPayload(values, { code: 'HSP05', kind: 'collective', mode: 'prayer_target' }, members, houses)
  assert.deepEqual(payload.attendees, [])
  const competition = activityPayload({ ...values, exemptions: {}, marks: { 1: '90', 2: '90' } }, { code: 'HKN01', kind: 'collective', mode: 'competition' }, members, houses)
  assert.deepEqual(competition.results, [{ house: 1, marks: '90' }, { house: 2, marks: '90' }])
})

test('portal panels show own totals, reversal, own-house ranking and aggregate standings', () => {
  const html = renderToStaticMarkup(createElement(Panels, { data: {
    ready: true, total: 3, page: 1, page_size: 25, count: 2, house: 'House One',
    history: [{ id: 1, activity: '<unsafe>', date: '2026-12-20', house: 'House One', points: 5, reversed: true }, { id: 2, activity: 'Arrival before adhān', date: '2026-12-20', house: 'House One', points: 3 }],
    house_leaderboard: [{ rank: 1, name: 'Camper A.', points: 3, own: true }],
    standings_ready: true, standings: [{ house_id: 1, rank: 1, name: 'House One', net: 18 }, { house_id: 2, rank: 2, name: 'House Two', net: 10 }],
  } }))
  assert.match(html, /My verified points/)
  assert.match(html, /Reversed \(0\)/)
  assert.match(html, /Camper A\. \(You\)/)
  assert.match(html, /House Two/)
  assert.match(html, /&lt;unsafe&gt;/)
  assert.doesNotMatch(html, /<unsafe>/)
})

test('pending schema does not display invented zero personal points', () => {
  const html = renderToStaticMarkup(createElement(Panels, { data: { ready: false, message: 'Setup pending', standings_ready: false } }))
  assert.match(html, /Setup pending/)
  assert.doesNotMatch(html, /camper-point-total/)
})

test('selection unmounts scoring and requests abort; portal styles use document flow', () => {
  const dashboard = fs.readFileSync(new URL('../components/dic/CamperDashboard.jsx', import.meta.url), 'utf8')
  const scores = fs.readFileSync(new URL('../components/dic/CamperScores.jsx', import.meta.url), 'utf8')
  assert.match(dashboard, /CamperScores key=\{selected.key\}/)
  assert.match(scores, /return \(\) => controller.abort\(\)/)
  assert.match(scores, /state\?\.path !== path/)
  const css = fs.readFileSync(new URL('../pages/ParticipantPortal.css', import.meta.url), 'utf8')
  const scoringStyles = css.split('\n').filter(line => /camper-scoring|camper-score/.test(line)).join('\n')
  assert.doesNotMatch(scoringStyles, /overflow:\s*(auto|scroll)|position:\s*fixed|max-height:/)
})
