import { spawnSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { assertStagingArtifacts, stagingPaymentHeaders, stagingRedirects } from './staging-config.mjs'

const redirects = stagingRedirects(process.env)
const root = fileURLToPath(new URL('../', import.meta.url))
const vite = fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url))
const result = spawnSync(process.execPath, [vite, 'build', '--mode', 'staging'], {
  cwd: root, stdio: 'inherit', env: { ...process.env, VITE_API_BASE_URL: '/api/v1' },
})
if (result.error) throw result.error
if (result.status !== 0) process.exit(result.status || 1)
writeFileSync(new URL('../dist/_redirects', import.meta.url), redirects)
writeFileSync(new URL('../dist/_headers', import.meta.url), stagingPaymentHeaders)
assertStagingArtifacts(
  readFileSync(new URL('../dist/_redirects', import.meta.url), 'utf8'),
  readFileSync(new URL('../dist/_headers', import.meta.url), 'utf8'),
  process.env,
)
