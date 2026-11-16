import test from 'node:test'
import assert from 'node:assert/strict'
import { prefersNativeIOSControls } from '../components/dic/nativeIOSControls.js'

test('iPhone and iPad use native picker controls', () => {
  for (const userAgent of ['Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)', 'Mozilla/5.0 (iPad; CPU OS 16_2 like Mac OS X)', 'iPod']) {
    assert.equal(prefersNativeIOSControls({ userAgent, platform: 'iPhone', maxTouchPoints: 5 }), true)
  }
  assert.equal(prefersNativeIOSControls({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X)', platform: 'MacIntel', maxTouchPoints: 5 }), true)
})

test('desktop and Android retain the accessible custom picker controls', () => {
  assert.equal(prefersNativeIOSControls(null), false)
  assert.equal(prefersNativeIOSControls({ userAgent: 'Mozilla/5.0 (Windows NT 10.0)', platform: 'Win32', maxTouchPoints: 0 }), false)
  assert.equal(prefersNativeIOSControls({ userAgent: 'Mozilla/5.0 (Linux; Android 14)', platform: 'Linux armv8l', maxTouchPoints: 5 }), false)
  assert.equal(prefersNativeIOSControls({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X)', platform: 'MacIntel', maxTouchPoints: 0 }), false)
})
