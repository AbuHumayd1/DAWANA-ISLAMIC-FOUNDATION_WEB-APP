import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('media studio is a standalone protected route, not an operations subpage', () => {
  const app = read('../App.jsx')
  assert.match(app, /path="\/media-studio\/\*".*element=\{<MediaStudio\s*\/>\}/)
  assert.match(app, /path="\/dic\/operations\/\*".*element=\{<Operations\s*\/>\}/)
})
test('media team has a discreet footer entry next to admin and operations', () => {
  const site = read('../components/layout/SiteChrome.jsx')
  assert.match(site, /to="\/media-studio">Media Studio Login/)
  assert.match(site, /to="\/dic\/operations">Operations Portal/)
  assert.match(site, /Admin Login/)
})
test('studio operates within its own workspace, without Django Admin redirects', () => {
  const ui = read('../pages/MediaStudio.jsx')
  const api = read('./mediaStudioApi.js')
  assert.doesNotMatch(ui, /admin\/dic|\/admin\//)
  assert.match(ui, /studioLibrary\(/)
  assert.match(ui, /studioPublish\(/)
  assert.match(ui, /studioUpload\(/)
  assert.match(ui, /user\.owner/)
  assert.match(ui, /Escape/)
  assert.match(ui, /pointerdown/)
  assert.match(api, /credentials: 'include'/)
  assert.match(api, /'X-CSRFToken'/)
})
test('R2 is not accessed directly from the browser', () => {
  const ui = read('../pages/MediaStudio.jsx')
  const api = read('./mediaStudioApi.js')
  assert.doesNotMatch(ui + api, /r2\.cloudflarestorage\.com|AWS_ACCESS|secret_access_key/)
})
