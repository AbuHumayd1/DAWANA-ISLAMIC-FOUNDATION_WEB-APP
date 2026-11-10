// OWNER-RUN ONLY. Static loopback preview; no proxy, backend, fixtures or writes.
// CSP blocks all application API connections, remote images/media and form sends.
import http from 'node:http'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const root = path.resolve(fileURLToPath(new URL('../output/historical-recovery-sprint/operations-production-build/', import.meta.url)))
const entry = path.join(root, 'index.html')
await fs.access(entry)
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.woff': 'font/woff' }
const csp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'none'; img-src 'self' data:; media-src 'self'; font-src 'self'; frame-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'"
const server = http.createServer(async (request, response) => {
  response.setHeader('Content-Security-Policy', csp)
  response.setHeader('Cache-Control', 'no-store')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.setHeader('Referrer-Policy', 'no-referrer')
  if (!['GET', 'HEAD'].includes(request.method)) { response.writeHead(405); response.end(); return }
  try {
    const url = new URL(request.url, 'http://127.0.0.1:4189')
    const requested = decodeURIComponent(url.pathname)
    if (/^\/(api|admin)(\/|$)/.test(requested)) { response.writeHead(503); response.end('Backend disabled in static preview.'); return }
    const candidate = path.resolve(root, '.' + requested)
    if (candidate !== root && !candidate.startsWith(root + path.sep)) { response.writeHead(403); response.end(); return }
    let file = candidate
    try {
      const stat = await fs.stat(file)
      if (!stat.isFile()) file = entry
    } catch { file = path.extname(requested) ? null : entry }
    if (!file) { response.writeHead(404); response.end(); return }
    const actual = await fs.realpath(file)
    const actualRoot = await fs.realpath(root)
    if (!actual.startsWith(actualRoot + path.sep)) { response.writeHead(403); response.end(); return }
    const body = request.method === 'HEAD' ? undefined : await fs.readFile(actual)
    response.setHeader('Content-Type', types[path.extname(actual)] || 'application/octet-stream')
    response.writeHead(200)
    response.end(body)
  } catch { response.writeHead(400); response.end('Preview unavailable.') }
})
server.listen(4189, '127.0.0.1', () => console.log('Static isolated preview: http://127.0.0.1:4189 — API access disabled. Stop with Ctrl+C.'))
