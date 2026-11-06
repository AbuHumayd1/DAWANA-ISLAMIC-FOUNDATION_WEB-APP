import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveMediaUrl } from './mediaUrl.js'

test('separate same-site HTTPS API serves editorial routes and authorized card navigation', () => {
  const api = 'https://api.example.org/api/v1'
  for (const path of ['/api/v1/dic/promotions/1/video/', '/api/v1/dic/flyer/1/',
    '/api/v1/dic/participant/enrollments/id/card/?format=portrait']) {
    assert.equal(resolveMediaUrl(path, api), 'https://api.example.org' + path)
  }
  assert.equal(resolveMediaUrl('https://bucket.r2.dev/participants/portraits/id.jpg', api), '')
})

test('API-origin media and downloads preserve paths, query and fragment', () => {
  const path = '/api/v1/dic/participant/enrollments/id/card/?format=portrait&download=1#page=1'
  assert.equal(resolveMediaUrl(path, 'https://api.example.test/api/v1'), 'https://api.example.test' + path)
  assert.equal(resolveMediaUrl(path, '/api/v1'), path)
  assert.equal(resolveMediaUrl('dic/memories/1/?preview=1', 'https://api.example.test/api/v1/'), 'https://api.example.test/api/v1/dic/memories/1/?preview=1')
  assert.equal(resolveMediaUrl('/api/v1/dic/photo/', 'http://localhost:8001/api/v1'), 'http://localhost:8001/api/v1/dic/photo/')
})

test('media resolver rejects object endpoints, credentials, foreign origins and unsafe paths', () => {
  for (const path of ['https://bucket.r2.dev/key', 'https://other.test/api/v1/file', '//evil.test/api/v1/file',
    'javascript:alert(1)', 'data:image/png,test', '/admin/', '../private/', '/api/v10/file',
    'https://user:password@api.example.test/api/v1/file', '/api/v1/\\evil', null]) {
    assert.equal(resolveMediaUrl(path, 'https://api.example.test/api/v1'), '')
  }
})
