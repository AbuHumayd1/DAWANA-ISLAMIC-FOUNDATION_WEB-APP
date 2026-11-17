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

test('Foundation publishing panel remains in the standalone Studio and uses scoped backend catalogue', () => {
  const studio = read('../pages/MediaStudio.jsx')
  const panel = read('../pages/StudioDestinations.jsx')
  const api = read('./mediaStudioApi.js')
  assert.match(studio, /<StudioDestinations /)
  assert.match(panel, /studioLinkAsset/)
  assert.match(panel, /studioPlacement/)
  assert.match(panel, /studioArchiveAsset/)
  assert.match(panel, /studioAssetMetadata/)
  assert.match(panel, /camper_resources/)
  assert.match(api, /\/assets\//)
  assert.doesNotMatch(panel, /r2\.cloudflarestorage\.com|AWS_ACCESS|\/admin\//)
})

test('public site and DIC landing consume only explicitly published destination feed', () => {
  const home = read('../pages/Home.jsx')
  const dic = read('../pages/DIC.jsx')
  const media = read('../pages/Media.jsx')
  const gallery = read('../components/media/PublishedStudioArchive.jsx')
  assert.match(home, /<PublishedStudioArchive destination="foundation_home"/)
  assert.match(dic, /<PublishedStudioArchive destination="dic_landing"/)
  assert.match(media, /<PublishedStudioArchive\s*\/>/)
  assert.match(gallery, /public-placements/)
  assert.match(gallery, /credentials: 'omit'/)
  assert.match(gallery, /foundation_archive/)
  assert.doesNotMatch(gallery, /camper_resources/)
})

test('YouTube live and recorded links are a separate R2-independent bulk workflow', () => {
  const studio = read('../pages/MediaStudio.jsx')
  const api = read('./mediaStudioApi.js')
  const pub = read('../components/media/PublishedStudioArchive.jsx')
  const dic = read('../pages/DIC.jsx')
  assert.match(studio, /key: 'hosted'/)
  assert.match(studio, /studioHostedLinks\(entries\)/)
  assert.match(studio, /25 YouTube\/Vimeo links|25 links per batch/)
  assert.match(studio, /No file upload or R2 storage required/)
  assert.match(api, /\/hosted-links\//)
  assert.match(pub, /approvedVideoLink\(row.embed_url\)/)
  assert.match(pub, /Play YouTube video or livestream/)
  assert.match(dic, /<PublishedStudioArchive destination="dic_resources"/)
})
