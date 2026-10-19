import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { visibleOperationsNavigation } from './operationsNavigation.js'

const script = fs.readFileSync(new URL('../../public/appearance.js', import.meta.url), 'utf8')
function environment(saved, dark = false, blocked = false) {
  const events = {}
  const media = { matches: dark, addEventListener: (_, fn) => { events.os = fn } }
  const storage = new Map(saved ? [['dawana.appearance', saved]] : [])
  const html = { dataset: {}, style: {} }
  const document = { documentElement: html, querySelectorAll: () => [], addEventListener: (event, fn) => { events[event] = fn } }
  const window = { document, matchMedia: () => media, localStorage: {
    getItem: (key) => { if (blocked) throw new Error('blocked'); return storage.get(key) },
    setItem: (key, value) => { if (blocked) throw new Error('blocked'); storage.set(key, value) },
  }, addEventListener: (name, fn) => { events[name] = fn } }
  vm.runInNewContext(script, { window })
  return { window, html, storage, events, media, controller: window.DawanaAppearance }
}
test('initial system theme resolves before rendering and follows OS changes', () => {
  const e = environment(null, true)
  assert.equal(e.html.dataset.theme, 'dark')
  assert.equal(e.html.dataset.readingSize, undefined)
  e.media.matches = false; e.events.os()
  assert.equal(e.html.dataset.theme, 'light')
  e.controller.toggle(); e.events.os()
  assert.equal(e.html.dataset.theme, 'dark')
})
test('explicit preferences persist across page loads and synchronize tabs', () => {
  const e = environment()
  e.controller.toggle()
  const next = environment(e.storage.get('dawana.appearance'))
  assert.equal(next.html.dataset.theme, 'dark')
  assert.equal(next.html.dataset.readingSize, undefined)
  next.storage.set('dawana.appearance', JSON.stringify({ theme: 'light', size: 'standard' }))
  next.events.storage({ key: 'dawana.appearance' })
  assert.equal(next.html.dataset.theme, 'light')
  assert.equal(next.html.dataset.readingSize, undefined)
  assert.equal(JSON.parse(next.storage.get('dawana.appearance')).size, undefined)
})
test('invalid preferences and blocked storage remain usable', () => {
  for (const value of ['invalid-json', '{"theme":"unknown","size":"huge"}']) {
    assert.equal(environment(value).controller.getSnapshot().theme, 'light')
  }
  const e = environment(null, false, true)
  assert.doesNotThrow(() => e.controller.toggle())
  assert.equal(e.html.dataset.theme, 'dark')
})
test('toggle notifies subscribers and retires size without losing other preferences', () => {
  const e = environment('{"theme":"system","size":"large","other":"keep"}', true)
  let notifications = 0
  const unsubscribe = e.controller.subscribe(() => notifications++)
  e.controller.toggle()
  assert.equal(e.html.dataset.theme, 'light')
  e.controller.toggle()
  assert.equal(e.html.dataset.theme, 'dark')
  assert.equal(notifications, 2)
  const saved = JSON.parse(e.storage.get('dawana.appearance'))
  assert.equal(saved.size, undefined)
  assert.equal(saved.other, 'keep')
  unsubscribe(); e.controller.toggle()
  assert.equal(notifications, 2)
})

test('Admin switch uses the same theme persistence as React, including icon clicks', () => {
  const e = environment()
  e.events.click({ target: { closest: (selector) => selector === '[data-appearance-toggle]' } })
  assert.equal(JSON.parse(e.storage.get('dawana.appearance')).theme, 'dark')
  e.events.click({ target: { closest: () => null } })
  assert.equal(e.html.dataset.theme, 'dark')
})

test('appearance initialization precedes styles and the React entrypoint', () => {
  const html = fs.readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
  assert.ok(html.indexOf('/appearance.js') < html.indexOf('/theme.css'))
  assert.ok(html.indexOf('/appearance.js') < html.indexOf('/src/main.jsx'))
})
test('portal navigation retains permission restrictions and its existing routes', () => {
  const operator = visibleOperationsNavigation({ permissions: {} })
  assert.deepEqual(operator.map((item) => item.label), ['Overview', 'Registrations', 'Participants', 'House allocation'])
  const authorized = visibleOperationsNavigation({ permissions: { finance: true, audit: true, export_reports: true } })
  assert.equal(authorized.length, 7)
  assert.ok(authorized.every((item) => item.to.startsWith('/dic/operations')))
})
test('semantic text pairs meet WCAG AA contrast in both palettes', () => {
  const css = fs.readFileSync(new URL('../../public/theme.css', import.meta.url), 'utf8')
  const palettes = [...css.matchAll(/:root(?:\[data-theme="dark"\])?\s*\{([^}]+)\}/g)].map((m) => Object.fromEntries([...m[1].matchAll(/--([\w-]+):\s*(#[\da-f]{6})/gi)].map((v) => [v[1], v[2]])))
  function luminance(hex) {
    const channels = [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255).map((n) => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4)
    return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722
  }
  const base = palettes[0]
  for (const changes of palettes) {
    const p = { ...base, ...changes }
    for (const [fg, bg] of [['text-main','page'],['text-muted','page'],['text-muted','panel'],['text-muted','panel-soft'],['heading','panel'],['success-text','success-bg'],['warning-text','warning-bg'],['danger-text','danger-bg'],['on-brand','brand-solid'],['on-brand','brand-deep'],['text-main','panel-soft'],['text-muted','panel-soft'],['heading','panel-soft'],['accent','panel-soft'],['brand-deep','accent-bright']]) {
      const a = luminance(p[fg]), b = luminance(p[bg])
      assert.ok((Math.max(a,b) + .05) / (Math.min(a,b) + .05) >= 4.5, `${fg} on ${bg}`)
    }
  }
})
