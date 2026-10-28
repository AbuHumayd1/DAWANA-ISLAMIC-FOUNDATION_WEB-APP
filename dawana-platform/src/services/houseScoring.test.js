import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { scoringPath, scorePayload, submissionReference } from './houseScoring.js'
import { visibleOperationsNavigation } from './operationsNavigation.js'
import { getScoringPrintUrl } from './operationsApi.js'

let server, Leaderboard, History
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  const module = await server.ssrLoadModule('/src/pages/HouseScoring.jsx')
  Leaderboard = module.CombinedLeaderboard; History = module.ScoreHistory
})
after(async () => { await server?.close() })
const render = (component, props) => renderToStaticMarkup(createElement(component, props))

test('scoring queries isolate edition, validate page and build existing-base print URLs', () => {
  assert.equal(scoringPath('41', 2), '/scoring/?page=2&edition=41')
  for (const edition of ['0', '-1', '../', '41&edition=42']) assert.throws(() => scoringPath(edition))
  for (const page of [NaN, 0, -1, 1.5]) assert.throws(() => scoringPath('41', page))
  assert.match(getScoringPrintUrl('41', 'history'), /\/dic\/operations\/scoring\/\?page=1&edition=41&print=history$/)
  assert.throws(() => getScoringPrintUrl('41', 'arbitrary'))
})

test('score form values require positive whole points and an activity without inventing categories', () => {
  const valid = { house: '2', entry_type: 'award', points: '12', activity: ' Agreed activity ', note: ' note ' }
  assert.deepEqual(scorePayload(valid), { house: 2, entry_type: 'award', points: 12, activity: 'Agreed activity', note: 'note' })
  for (const points of ['0', '-1', '1.5', '1e2', '2147483648', '', 'NaN']) assert.throws(() => scorePayload({ ...valid, points }))
  assert.throws(() => scorePayload({ ...valid, activity: ' ' }))
  assert.throws(() => scorePayload({ ...valid, house: '' }))
  assert.throws(() => scorePayload({ ...valid, entry_type: 'penalty' }))
  assert.equal(scorePayload({ ...valid, entry_type: 'deduction' }).points, 12)
})

test('retries reuse submission references; changed or successfully reset entries get fresh references', () => {
  let calls = 0
  const makeId = () => `synthetic-${++calls}`
  const first = submissionReference(null, { points: 4 }, makeId)
  assert.equal(submissionReference(first, { points: 4 }, makeId), first)
  assert.notEqual(submissionReference(first, { points: 5 }, makeId).id, first.id)
  assert.notEqual(submissionReference(null, { points: 4 }, makeId).id, first.id)
  assert.equal(calls, 3)
})

test('combined table retains backend tie ranks, both genders, zero and negative values and configured colours', () => {
  const rows = [
    { house_id: 1, name: 'Male House', rank: 1, colour: '#123456', awarded: 8, deducted: 0, net: 8 },
    { house_id: 2, name: 'Female House', rank: 1, colour: null, awarded: 10, deducted: 2, net: 8 },
    { house_id: 3, name: 'Zero House', rank: 3, colour: null, awarded: 0, deducted: 0, net: 0 },
    { house_id: 4, name: '<Negative>', rank: 4, colour: null, awarded: 0, deducted: 3, net: -3 },
  ]
  const markup = render(Leaderboard, { rows })
  for (const text of ['Male House', 'Female House', 'Zero House', '-3', 'Colour not configured', '#123456', '&lt;Negative&gt;']) assert.ok(markup.includes(text))
  assert.equal((markup.match(/<td>1<\/td>/g) || []).length, 2)
  assert.match(render(Leaderboard, { rows: [] }), /No participant houses configured/)
})

test('history preserves reversal links and permits correction only for original unreversed entries', () => {
  const original = { id: 1, house: 'House One', activity: 'Activity', entry_type: 'award', points: 5, staff: 'Staff', time: '2026-12-20T08:00:00Z', note: 'Note', reverses: null, reversed_by: null }
  assert.match(render(History, { rows: [original], canCorrect: true, busy: false }), /Reverse entry/)
  assert.doesNotMatch(render(History, { rows: [original], canCorrect: false }), /<button/)
  const markup = render(History, { rows: [{ ...original, reversed_by: 2 }, { ...original, id: 2, reverses: 1 }], canCorrect: true })
  assert.match(markup, /Reversed by entry #2/)
  assert.match(markup, /reverses entry #1/)
  assert.doesNotMatch(markup, /<button/)
  assert.match(render(History, { rows: [], canCorrect: true }), /No scoring entries yet/)
})

test('existing scoring route is live and visible only with explicit read permission and campsite access', () => {
  const links = (access, scores) => visibleOperationsNavigation({ can_access_campsite: access, permissions: { scores } }).filter(item => item.to.endsWith('/scoring'))
  assert.equal(links(false, true).length, 0)
  assert.equal(links(true, false).length, 0)
  assert.equal(links(true, true).length, 1)
  assert.equal(links(true, true)[0].planned, undefined)
})

test('leaderboard description and empty state stay outside the horizontal table scroller', () => {
  const markup = render(Leaderboard, { rows: [] })
  const description = markup.indexOf('<p class="score-caption">')
  const scrollRegion = markup.indexOf('<div class="ops-table-wrap score-table-scroll"')
  const emptyState = markup.indexOf('<p>No participant houses configured')
  assert.ok(description >= 0 && description < scrollRegion)
  assert.ok(markup.indexOf('</table></div>') < emptyState)
  assert.match(markup, /<table[^>]+aria-label="Combined house leaderboard"/)
})
