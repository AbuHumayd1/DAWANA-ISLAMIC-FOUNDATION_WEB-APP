import test from 'node:test'
import assert from 'node:assert/strict'
import { previewMiddleware, validatePreviewOptions } from '../../scripts/preview-dic-registration.mjs'

const options = { registration_is_open: true, categories: [{ id: 923, name: 'Synthetic unit-test category', current_fee_ngn: '123.45' }] }
function request(method, url) {
  const response = { headers: {}, setHeader(key, value) { this.headers[key] = value }, end(body) { this.body = body } }
  let forwarded = false
  previewMiddleware(options)({ method, url }, response, () => { forwarded = true })
  return { ...response, forwarded }
}

test('preview serves the unchanged options snapshot and leaves document/static frontend loading alone', () => {
  const response = request('GET', '/api/v1/dic/registration-options/?preview=1')
  assert.equal(response.statusCode, 200)
  assert.deepEqual(JSON.parse(response.body), options)
  assert.equal(response.headers['Cache-Control'], 'no-store')
  assert.equal(response.forwarded, false)
  assert.equal(request('GET', '/dic/register').forwarded, true)
  assert.equal(request('GET', '/src/pages/DIC.jsx').forwarded, true)
})

test('preview cannot forward order, payment, recovery, admin or other backend requests', () => {
  for (const path of ['/api/v1/dic/orders/', '/api/v1/dic/orders/test/payments/initialize/', '/api/v1/dic/orders/test/payments/test/verify/', '/api/v1/dic/orders/test/pricing/accept/', '/api/v1/dic/tester-access/login/', '/api/v1/dic/recovery/channels/', '/api/anything', '/admin/', '/static/admin/test.css']) {
    for (const method of ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD']) {
      const response = request(method, path)
      assert.equal(response.statusCode, 403)
      assert.equal(response.forwarded, false)
      assert.equal(JSON.parse(response.body).code, 'local_preview_read_only')
    }
  }
  assert.equal(request('POST', '/api/v1/dic/registration-options/').statusCode, 403)
  assert.equal(request('POST', '/dic/register').statusCode, 403)
})

test('preview never overrides registration availability or invents missing categories', () => {
  for (const invalid of [null, {}, { ...options, registration_is_open: false }, { ...options, categories: [] }]) {
    assert.throws(() => validatePreviewOptions(invalid))
  }
  assert.equal(validatePreviewOptions(options), options)
})
