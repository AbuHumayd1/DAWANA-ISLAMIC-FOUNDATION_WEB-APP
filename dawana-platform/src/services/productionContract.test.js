import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { productionApiBase, privateDraft, registrationSubmission } from './productionContract.js'
import { primaryRegistrantPayload, registrationCredentialsPayload } from './bookingContact.js'

test('production API requires exact relative same-origin namespace', () => {
  assert.equal(productionApiBase(), '/api/v1')
  for (const base of ['https://api.example.test/api/v1', '//evil.test/api/v1', '/api', 'javascript:alert(1)']) {
    assert.throws(() => productionApiBase(base))
  }
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
  const credentials = { password, password_confirmation: password }
  const submit = value => registrationSubmission(value, credentials, primaryRegistrantPayload, row => row, registrationCredentialsPayload)
  assert.deepEqual(submit(flow), submit({ ...flow, submissionUncertain: true }))
  assert.equal(submit(flow).primary_registrant.email, 'guardian@example.test')
  assert.equal(submit(flow).portal_account.password, password)
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
