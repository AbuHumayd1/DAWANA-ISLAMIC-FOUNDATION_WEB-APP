import test from 'node:test'
import assert from 'node:assert/strict'
import { stagingRedirects } from '../../scripts/staging-config.mjs'
const env = { DAWANA_STAGING_FRONTEND: 'true', SITE_ID: 'isolated-test-site', DAWANA_STAGING_SITE_ID: 'isolated-test-site', STAGING_BACKEND_ORIGIN: 'https://dawana-staging-test.onrender.com' }

test('staging frontend proxy keeps API, Admin and static paths before SPA fallback', () => {
  const rules = stagingRedirects(env).split('\n')
  assert.equal(rules[0], '/api/* https://dawana-staging-test.onrender.com/api/:splat 200!')
  assert.ok(rules[1].startsWith('/admin/* '))
  assert.ok(rules[2].startsWith('/static/* '))
  assert.equal(rules[3], '/* /index.html 200')
})
test('staging build rejects unapproved sites, cross-site API bases and malformed backend URLs', () => {
  for (const patch of [{ DAWANA_STAGING_FRONTEND: '' }, { SITE_ID: 'live-site' }, { VITE_API_BASE_URL: 'https://backend.example/api/v1' }, { STAGING_BACKEND_ORIGIN: 'http://localhost:8000' }, { STAGING_BACKEND_ORIGIN: 'https://user:pass@dawana-staging-test.onrender.com' }, { STAGING_BACKEND_ORIGIN: 'https://dawana-staging-test.onrender.com/path' }]) {
    assert.throws(() => stagingRedirects({ ...env, ...patch }))
  }
})
