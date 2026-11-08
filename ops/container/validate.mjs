// Offline packaging contract checks; never reads environment files or secrets.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { execFileSync } from 'node:child_process'

const read = path => fs.readFileSync(path, 'utf8')
const docker = read('Dockerfile')
assert.equal((docker.match(/^FROM /gm) || []).length, 3)
assert.match(docker, /RUN npm ci/)
assert.match(docker, /USER 10001:10001/)
assert.match(docker, /tini.*entrypoint.py/)
assert.doesNotMatch(docker, /COPY\s+\.\s|manage\.py\s+(migrate|createsuperuser|createcachetable)/)
const ignore = read('.dockerignore')
for (const rule of ['**', '**/.env', '**/.env.*', '**/*.key', '**/*.sqlite*', '**/media', '**/uploads', '**/.git', '**/node_modules']) {
  assert(ignore.split(/\r?\n/).includes(rule), 'Missing context exclusion: ' + rule)
}
const files = execFileSync('git', ['ls-files', 'backend', 'dawana-platform/public'], { encoding: 'utf8' }).trim().split(/\r?\n/)
// Existing tracked example env files are legitimate repository documentation;
// Docker excludes them too. Check their exclusion, without opening any of them.
for (const path of files.filter(path => /(^|\/)\.env($|\.)/.test(path))) {
  assert(ignore.includes('**/.env.*') && ignore.includes('**/.env'))
}
for (const path of ['ops/container/entrypoint.py', 'ops/container/gateway.py', 'ops/container/healthcheck.py',
  'ops/container/runtime_config.py', 'ops/container/process_failure.py', 'ops/container/static_settings.py', 'ops/container/supervisord.conf', 'ops/container/smoke.sh']) {
  assert(!read(path).includes('\r'), 'Container scripts/config must use LF: ' + path)
}
assert.match(read('ops/container/entrypoint.py'), /child\.wait\(\)/)
assert.match(read('ops/container/entrypoint.py'), /child-failed/)
assert.match(read('ops/container/supervisord.conf'), /autorestart=false/)
assert.match(read('ops/container/smoke.sh'), /test.*503/)
assert.match(read('ops/container/smoke.sh'), /chmod 755 "\$evidence"/)
assert.match(read('ops/container/healthcheck.py'), /ProxyHandler\(\{\}\)/)
for (const path of ['ops/container/smoke.sh', 'ops/container/smoke-edge.sh']) {
  assert.match(read(path), /timeout 60s docker wait/)
}
console.log('PASS: offline container build/context and startup contract checks (runtime not executed).')
