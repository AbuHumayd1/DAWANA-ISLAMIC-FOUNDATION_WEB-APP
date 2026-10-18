import test from 'node:test'
import assert from 'node:assert/strict'
import { getOperationsData, signIn, signOut } from './operationsApi.js'

test('session requests include cookies, refresh rotated CSRF, and protect logout', async () => {
  const calls = []
  const original = globalThis.fetch
  let tokens = 0
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/csrf/')) return Response.json({ csrfToken: `csrf-${++tokens}` })
    if (url.endsWith('/logout/')) return new Response(null, { status: 204 })
    return Response.json({ username: 'test-only' })
  }
  try {
    await signIn('test-only', 'test-only')
    await signOut()
    assert.equal(calls.length, 4)
    assert.ok(calls.every(({ options }) => options.credentials === 'include'))
    assert.equal(calls[1].options.headers.get('X-CSRFToken'), 'csrf-1')
    assert.equal(calls[3].options.headers.get('X-CSRFToken'), 'csrf-2')
  } finally { globalThis.fetch = original }
})

test('expired sessions notify the protected application and preserve the HTTP error', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  const events = []
  globalThis.window = { dispatchEvent: (event) => events.push(event.type) }
  globalThis.fetch = async () => Response.json({ detail: 'Authentication credentials were not provided.' }, { status: 403 })
  try {
    await assert.rejects(getOperationsData('/dashboard/'), (error) => error.status === 403)
    assert.deepEqual(events, ['operations-session-expired'])
  } finally {
    globalThis.fetch = originalFetch
    globalThis.window = originalWindow
  }
})

test('permission denial remains visible without expiring a valid session', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  const events = []
  globalThis.window = { dispatchEvent: (event) => events.push(event.type) }
  globalThis.fetch = async () => Response.json({ detail: 'You do not have permission to perform this action.' }, { status: 403 })
  try {
    await assert.rejects(getOperationsData('/payments/'), /permission/)
    assert.deepEqual(events, [])
  } finally {
    globalThis.fetch = originalFetch
    globalThis.window = originalWindow
  }
})
