import test from 'node:test'
import assert from 'node:assert/strict'
import { assertStagingArtifacts, stagingPaymentHeaders, stagingRedirects } from '../../scripts/staging-config.mjs'
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

test('publish artifact checks reject SPA-first routing, duplicate proxies and missing privacy headers', () => {
  const redirects = stagingRedirects(env)
  assertStagingArtifacts(redirects, stagingPaymentHeaders, env)
  assert.match(stagingPaymentHeaders, /^\/dic\/register\/\*\n  Referrer-Policy: no-referrer\n$/)
  for (const invalid of ['/* /index.html 200\n' + redirects, redirects + redirects, '/* /index.html 200\n']) {
    assert.throws(() => assertStagingArtifacts(invalid, stagingPaymentHeaders, env))
  }
  assert.throws(() => assertStagingArtifacts(redirects, '', env))
  for (const path of ['/api/v1/dic/orders/', '/api/v1/dic/payments/return/', '/api/v1/dic/registration-options/?edition=1']) {
    const rule = redirects.split('\n').find((line) => path.startsWith(line.split('*')[0]))
    assert.ok(rule.startsWith('/api/* '))
    const target = rule.split(' ')[1].replace(':splat', path.slice('/api/'.length))
    assert.equal(target, env.STAGING_BACKEND_ORIGIN + path)
  }
})
