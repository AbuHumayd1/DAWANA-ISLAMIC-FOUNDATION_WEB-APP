import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import postcss from 'postcss'
import { assignmentPayload, draftPayload, localDateTime, managementPath } from './campManagement.js'
import { visibleOperationsNavigation, visibleOperationsGroups } from './operationsNavigation.js'

let server, ui
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  ui = await server.ssrLoadModule('/src/pages/CampManagement.jsx')
})
after(async () => { await server?.close() })
const render = (name, props = {}) => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(ui[name], props)))
const read = path => fs.readFileSync(new URL(path, import.meta.url), 'utf8')
const target = { id: 2, name: 'Approved class', active: true }
const camper = { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', name: 'Synthetic Camper', assignment: null }

test('management paths enforce explicit edition and known private resources', () => {
  assert.equal(managementPath('/classes/', 41, { q: 'A & B', active: 'true', page: 2 }), '/classes/?edition=41&q=A+%26+B&active=true&page=2')
  assert.equal(new URLSearchParams(managementPath('/announcements/3/publication/', 41, { edition: 99 }).split('?')[1]).get('edition'), '41')
  for (const edition of ['', 0, -1, 'invalid']) assert.throws(() => managementPath('/classes/', edition))
  for (const path of ['/admin/', '/classes/0/', '/payments/', 'https://evil.test']) assert.throws(() => managementPath(path, 41))
  assert.match(managementPath('/camp-management/announcements/history/', 41), /^\/camp-management\/announcements\/history\//)
})

test('assignment payload distinguishes new assignment from reviewed transfer', () => {
  assert.deepEqual(assignmentPayload(camper, target, ' Reviewed assignment '), { participant: camper.id, academic_class: 2, reason: 'Reviewed assignment' })
  const assigned = { ...camper, assignment: { id: 7, academic_class: 1, version: '2026-11-09T12:00:00+00:00' } }
  assert.deepEqual(assignmentPayload(assigned, target, 'Transfer'), { participant: camper.id, academic_class: 2, assignment: 7, version: assigned.assignment.version, reason: 'Transfer' })
  for (const destination of [null, { ...target, active: false }]) assert.throws(() => assignmentPayload(camper, destination, 'Reason'))
  assert.throws(() => assignmentPayload(camper, target, '   '))
  assert.throws(() => assignmentPayload(camper, target, 'x'.repeat(501)))
  assert.throws(() => assignmentPayload({ ...camper, assignment: { academic_class: 2 } }, target, 'No change'))
})

test('draft payload cannot set audience or publication state and carries exact version', () => {
  const values = { title: ' Title ', body: ' Body ', starts_at: '2026-12-24T10:00:00Z', ends_at: '2026-12-24T11:00:00Z', status: 'published', audience: 'public' }
  const payload = draftPayload(values, { version: 'original-token' })
  assert.deepEqual(payload, { title: 'Title', body: 'Body', starts_at: '2026-12-24T10:00:00.000Z', ends_at: '2026-12-24T11:00:00.000Z', version: 'original-token' })
  assert.deepEqual(draftPayload({ title: 'Title', body: 'Body', starts_at: '', ends_at: '' }), { title: 'Title', body: 'Body', starts_at: null, ends_at: null })
  for (const mutation of [{ title: '' }, { body: ' ' }, { title: 'x'.repeat(161) }, { body: 'x'.repeat(5001) }, { starts_at: 'bad' }, { ends_at: values.starts_at }]) assert.throws(() => draftPayload({ ...values, ...mutation }))
  assert.equal(localDateTime(''), '')
  assert.match(localDateTime('2026-12-24T10:00:00Z'), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/)
})

test('editor navigation needs campsite authority and each explicit domain permission', () => {
  for (const campsite of [false, true]) for (const classes of [false, true]) for (const announcements of [false, true]) {
    const user = { can_access_campsite: campsite, permissions: { classes, announcements } }
    const links = visibleOperationsNavigation(user).map(row => row.to)
    assert.equal(links.includes('/dic/operations/classes'), campsite && classes)
    assert.equal(links.includes('/dic/operations/announcements'), campsite && announcements)
    const grouped = visibleOperationsGroups(user).flatMap(group => group.items.map(row => row.to))
    assert.deepEqual([...grouped].sort(), [...links].sort())
  }
})

test('class editing uses existing name and activation controls without fabricated capacity or teachers', () => {
  const html = render('ClassEditor', { row: { id: 1, name: '<Approved>', active: true, version: 'v' }, onSave() {}, onCancel() {} })
  assert.match(html, /Edit class/)
  assert.match(html, /value="&lt;Approved&gt;"/)
  assert.match(html, /maxLength="120"/)
  assert.match(html, /Active class/)
  assert.doesNotMatch(html, /name="(?:capacity|teacher|edition)"/)
  const disabled = render('ClassEditor', { busy: true, onSave() {}, onCancel() {} })
  assert.match(disabled, /fieldset disabled=""/)
})

test('assignment form presents source destination and explicit consequential-action confirmation', () => {
  const html = render('AssignmentEditor', { camper: { ...camper, assignment: { class_name: 'Previous class' } }, target, onSave() {}, onCancel() {} })
  for (const text of ['Review class transfer', 'Previous class', 'Approved class', 'Confirm transfer', 'I confirm the camper']) assert.ok(html.includes(text))
  assert.match(html, /maxLength="500"/)
  assert.match(html, /type="checkbox" required=""/)
  assert.doesNotMatch(html, /Delete assignment|End assignment|Teacher assignment/)
})

test('announcement preview escapes markup and remains visibly a preview', () => {
  const html = render('AnnouncementPreview', { title: '<script>title</script>', body: '<img src=x onerror=alert(1)>\nSecond line' })
  assert.match(html, /&lt;script&gt;title&lt;\/script&gt;/)
  assert.match(html, /&lt;img/)
  assert.doesNotMatch(html, /<script>|<img|dangerouslySetInnerHTML/)
  assert.match(html, /Saving a draft does not publish/)
})

test('draft form offers time windows without a publish shortcut', () => {
  const html = render('AnnouncementEditor', { onSave() {}, onCancel() {} })
  assert.match(html, /Save draft/)
  assert.equal((html.match(/type="datetime-local"/g) || []).length, 2)
  assert.match(html, /maxLength="5000"/)
  assert.doesNotMatch(html, /Confirm publication|Publish now|Audience<select/)
})

test('publication and withdrawal require reason and confirmation and preserve original state', () => {
  for (const [status, label] of [['draft', 'Confirm publication'], ['published', 'Confirm withdrawal']]) {
    const html = render('PublicationEditor', { row: { status, title: 'Announcement', body: 'Text', version: 'v' }, onSave() {}, onCancel() {} })
    assert.ok(html.includes(label))
    assert.match(html, /type="checkbox" required=""/)
    assert.match(html, /textarea required=""/)
    assert.match(html, /maxLength="500"/)
  }
})

test('entry pages require an explicit edition and show loading without making writes', () => {
  for (const name of ['ClassesOperations', 'AnnouncementsOperations']) {
    const html = render(name, { user: { permissions: {} } })
    assert.match(html, /Choose a camp edition/)
    assert.match(html, /Loading camp records/)
    assert.doesNotMatch(html, /Open Django Admin|Synthetic Camper/)
  }
})

test('direct URL guards are independent of sidebar visibility and public return link remains', () => {
  const source = read('../pages/Operations.jsx')
  assert.match(source, /path="classes" element=\{user\.can_access_campsite && user\.permissions\.classes \? <ClassesOperations/)
  assert.match(source, /path="announcements" element=\{user\.can_access_campsite && user\.permissions\.announcements \? <AnnouncementsOperations/)
  for (const route of ['timetables', 'check-in', 'registrations', 'assisted-registration', 'participant-ids', 'finance', 'welfare', 'feedback']) assert.ok(source.includes(`path="${route}"`))
  assert.match(source, /Return to Main Website/)
  const overview = read('../pages/CampsiteFoundation.jsx')
  assert.match(overview, /user\.permissions\.classes && <Link to=\{`\/dic\/operations\/classes/)
  assert.match(overview, /user\.permissions\.announcements && <Link to=\{`\/dic\/operations\/announcements/)
  assert.match(overview, /encodeURIComponent\(data\.edition\.id\)/)
})

test('mobile structure scopes controls tables history and readable previews to management pages', () => {
  const css = read('../pages/CampManagement.css')
  postcss.parse(css).walkRules(rule => { for (const selector of rule.selectors) assert.match(selector, /^\.cm-/) })
  assert.match(css, /@media \(max-width:640px\)/)
  assert.match(css, /min-height:44px/)
  assert.match(css, /overflow-x:auto/)
  assert.match(css, /white-space:pre-wrap/)
  assert.match(css, /:focus-visible/)
})
