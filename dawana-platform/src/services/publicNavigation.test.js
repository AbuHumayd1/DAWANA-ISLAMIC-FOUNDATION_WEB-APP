import test from 'node:test'
import assert from 'node:assert/strict'
import { primaryNavigation, secondaryNavigation, navigation, isNavigationActive } from './publicNavigation.js'

test('desktop destinations are grouped without duplicates and all approved destinations remain reachable', () => {
  assert.deepEqual(primaryNavigation.map(([name]) => name), ['Home', 'About', 'Programs', 'Events', 'DIC'])
  assert.deepEqual(secondaryNavigation.map(([, path]) => path), ['/#what-we-do', '/projects', '/dic/participant', '/media', '/contact', '/get-involved', '/faq'])
  assert.equal(new Set(navigation.map(([, path]) => path)).size, navigation.length)
})

test('active state distinguishes home sections and participant access from the DIC registration routes', () => {
  for (const [location, expected] of [
    [{ pathname: '/', hash: '' }, '/'],
    [{ pathname: '/', hash: '#who-we-are' }, '/#who-we-are'],
    [{ pathname: '/', hash: '#what-we-do' }, '/#what-we-do'],
    [{ pathname: '/dic/register/recover', hash: '' }, '/dic'],
    [{ pathname: '/dic/participant', hash: '' }, '/dic/participant'],
    [{ pathname: '/programs', hash: '' }, '/programs'],
  ]) {
    assert.deepEqual(navigation.filter(([, href]) => isNavigationActive(href, location)).map(([, href]) => href), [expected])
  }
  assert.equal(isNavigationActive('/dic', { pathname: '/dictionary', hash: '' }), false)
})
