import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { productionApiBase, backendUrl, privateDraft, registrationSubmission } from './productionContract.js'
import { primaryRegistrantPayload, registrationCredentialsPayload } from './bookingContact.js'

test('production API accepts the separate HTTPS backend and rejects unsafe bases', () => {
  assert.throws(() => productionApiBase())
  assert.equal(productionApiBase('/api/v1'), '/api/v1')
  assert.equal(productionApiBase('https://api.example.test/api/v1'), 'https://api.example.test/api/v1')
  assert.equal(backendUrl('/admin/', 'https://api.example.test/api/v1'), 'https://api.example.test/admin/')
  assert.equal(backendUrl('/admin/', '/api/v1'), '/admin/')
  for (const base of ['http://api.example.test/api/v1', '//evil.test/api/v1', '/api', 'javascript:alert(1)',
    'https://user:password@api.example.test/api/v1', 'https://api.example.test/api/v1/',
    'https://api.example.test/api/v1?token=secret', 'https://api.example.test:444/api/v1',
    'https://api.example.test/api/v1#fragment']) {
    assert.throws(() => productionApiBase(base))
  }
})

test('explicit guardians use current participant identities and cannot silently shift after edits', () => {
  const flow = { participants: [{ id: 'adult' }, { id: 'child' }], primaryRegistrant: {
    guardianRelationships: [{ childId: 'child', guardianId: 'adult', confirmed: true }] } }
  const submit = value => registrationSubmission(value, {}, row => row, row => row, () => ({}))
  assert.deepEqual(submit(flow).guardian_relationships, [{ child_index: 1, guardian_index: 0, confirmed: true }])
  assert.throws(() => submit({ ...flow, participants: [{ id: 'child' }] }))
  assert.throws(() => submit({ ...flow, primaryRegistrant: { guardianRelationships: [{ childId: 'child', guardianId: 'adult', confirmed: false }] } }))
})

test('draft serialization drops all participant, contact, password and token data', () => {
  const saved = privateDraft({ participants: [{ fullName: 'Private' }], primaryRegistrant: { email: 'private@example.test' },
    password: 'private', access_token: 'private', orderSummary: { items: ['private'] }, orderId: 'order-id',
    idempotencyKey: 'retry-id', paymentStatus: 'pending', expiresAt: 123 })
  assert.equal(JSON.stringify(saved).includes('private'), false)
  assert.deepEqual(saved.participants, [])
  assert.equal(saved.orderId, 'order-id')
  assert.equal(saved.idempotencyKey, 'retry-id')
})

test('normal and uncertain retries retain complete payload and require password reentry', () => {
  const flow = { participants: [{ fullName: 'Camper' }], primaryRegistrant: { fullName: 'Guardian', email: 'guardian@example.test' } }
  const password = 'synthetic-password'
  const credentials = { username: 'synthetic-owner', password, password_confirmation: password }
  const submit = value => registrationSubmission(value, credentials, primaryRegistrantPayload, row => row, registrationCredentialsPayload)
  assert.deepEqual(submit(flow), submit({ ...flow, submissionUncertain: true }))
  assert.equal(submit(flow).primary_registrant.email, 'guardian@example.test')
  assert.equal(submit(flow).portal_account.password, password)
  assert.equal(submit(flow).portal_account.username, 'synthetic-owner')
  assert.throws(() => registrationSubmission(flow, {}, primaryRegistrantPayload, row => row, registrationCredentialsPayload))
  assert.throws(() => submit({ ...flow, participants: [] }))
})

test('gateway template reserves backend routes, overwrites client headers and disables private caching', () => {
  const config = fs.readFileSync(new URL('../../../ops/production/gateway.nginx.conf.example', import.meta.url), 'utf8')
  assert.match(config, /location ~ \^\/\(api\|admin\|static\)/)
  assert.match(config, /location ~ \^\/\(media\|health\)/)
  assert.match(config, /proxy_set_header X-Dawana-Client-IP \$remote_addr;/)
  assert.match(config, /proxy_set_header X-Forwarded-For "";/)
  assert.match(config, /proxy_pass http:\/\/127\.0\.0\.1:10000;/)
  assert.match(config, /proxy_cache off;/)
  assert.match(config, /private, no-store/)
  assert.match(config, /try_files \$uri \$uri\/ \/index.html;/)
})
