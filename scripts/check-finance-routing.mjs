// Anonymous, loopback-only GET checks. No sessions, mutations or payment calls.
import { mkdir, writeFile } from 'node:fs/promises'

function origin(value) {
  const url = new URL(value)
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
      || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('Use an HTTP loopback origin without credentials or a path.')
  }
  return url.origin
}
const backend = origin(process.argv[2] || 'http://127.0.0.1:8000')
const frontend = origin(process.argv[3] || 'http://127.0.0.1:5173')
const checks = []
for (let round = 1; round <= 3; round++) {
  for (const [service, base] of [['backend', backend], ['proxy', frontend]]) {
    for (const endpoint of ['finance/?metadata=1', 'auth/me/']) {
      const url = `${base}/api/v1/dic/operations/${endpoint}`
      try {
        const response = await fetch(url, {
          method: 'GET', redirect: 'manual', signal: AbortSignal.timeout(5000),
          headers: { Accept: 'application/json' },
        })
        const body = await response.text()
        let keys = [], detailIsString = false
        try {
          const data = JSON.parse(body)
          keys = Object.keys(data)
          detailIsString = typeof data.detail === 'string'
        } catch { /* HTML/proxy failures are summarized without saving bodies. */ }
        const patterns = [...body.matchAll(/<li>\s*([\s\S]*?)\s*<\/li>/g)]
          .map(match => match[1].replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim())
        const row = {
          round, service, url, status: response.status,
          contentType: response.headers.get('content-type'),
          server: response.headers.get('server'),
          cacheControl: response.headers.get('cache-control'),
          pragma: response.headers.get('pragma'), keys,
        }
        if (response.status === 404 && patterns.length) {
          row.urlconf = body.match(/URLconf defined in <code>([^<]*)<\/code>/)?.[1]
          row.financePatternListed = patterns.some(pattern => pattern.includes('operations-finance'))
          row.operationsPatternListed = patterns.some(pattern => pattern.includes('operations/auth/me/'))
        }
        row.pass = [401, 403].includes(row.status) && row.contentType?.includes('application/json')
          && keys.length === 1 && keys[0] === 'detail' && detailIsString
          && !!row.cacheControl?.includes('no-store') && row.pragma === 'no-cache'
        checks.push(row)
      } catch (error) {
        checks.push({ round, service, url, pass: false, error: error.message, cause: error.cause?.code })
      }
    }
  }
}
const report = {
  capturedAt: new Date().toISOString(), backend, frontend,
  scope: 'Three sequential rounds, anonymous GET only; no response bodies/cookies retained. No browser or financial acceptance claim.',
  passed: checks.filter(check => check.pass).length, total: checks.length,
  routingVerified: checks.every(check => check.pass), checks,
}
const directory = new URL('../output/acceptance/finance-routing/', import.meta.url)
await mkdir(directory, { recursive: true })
const destination = new URL(`routing-${new Date().toISOString().replace(/[:.]/g, '-')}.json`, directory)
await writeFile(destination, JSON.stringify(report, null, 2) + '\n')
console.log(JSON.stringify(report, null, 2))
console.log(`Evidence: ${destination.pathname}`)
process.exitCode = report.routingVerified ? 0 : 1
