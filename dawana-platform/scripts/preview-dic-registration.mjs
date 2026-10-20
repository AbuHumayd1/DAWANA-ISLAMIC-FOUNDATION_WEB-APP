// Explicit, local-only visual preview. Never imported by the application or build.
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const optionsUrl = 'https://dawana-islamic-foundation-web-app.onrender.com/api/v1/dic/registration-options/'

export function validatePreviewOptions(options) {
  if (options?.registration_is_open !== true || !Array.isArray(options.categories) || !options.categories.length) {
    throw new Error('Preview requires an open registration-options response with existing categories. No availability or pricing is overridden.')
  }
  return options
}

export function previewMiddleware(options) {
  const snapshot = JSON.stringify(validatePreviewOptions(options))
  return (request, response, next) => {
    const path = new URL(request.url, 'http://127.0.0.1').pathname
    // Match Vite's proxy prefixes, including malformed paths, before forwarding.
    const api = path.startsWith('/api')
    const admin = path.startsWith('/admin')
    const backendStatic = path.startsWith('/static')
    if (!api && !admin && !backendStatic && ['GET', 'HEAD'].includes(request.method)) return next()
    response.setHeader('Content-Type', 'application/json')
    response.setHeader('Cache-Control', 'no-store')
    if (path === '/api/v1/dic/registration-options/' && request.method === 'GET') {
      response.statusCode = 200
      response.end(snapshot)
    } else {
      response.statusCode = 403
      response.end(JSON.stringify({ code: 'local_preview_read_only', detail: 'Local visual preview only. Orders, payments, recovery and login are disabled; no request was forwarded to Django.' }))
    }
  }
}

async function main() {
  const args = process.argv.slice(2)
  if (args.length && (args.length !== 2 || args[0] !== '--options-file')) throw new Error('Usage: node scripts/preview-dic-registration.mjs [--options-file path-to-public-options.json]')
  let options
  if (args.length) {
    options = JSON.parse(await readFile(resolve(args[1]), 'utf8'))
  } else {
    const response = await fetch(optionsUrl, { credentials: 'omit', redirect: 'error', signal: AbortSignal.timeout(90000), headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error(`Public staging options returned HTTP ${response.status}; no server started.`)
    options = await response.json()
  }
  validatePreviewOptions(options)
  const { createServer } = await import('vite')
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api/v1') },
    plugins: [{ name: 'local-dic-read-only-preview', configureServer(server) { server.middlewares.use(previewMiddleware(options)) } }],
    server: { host: '127.0.0.1', port: 5179, strictPort: true, open: false },
  })
  await server.listen()
  console.log('Read-only DIC preview: http://127.0.0.1:5179/dic/register')
  console.log('Uses an unchanged public options snapshot. Backend requests are blocked. Stop with Ctrl+C.')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => {
    console.error('Preview could not start. Check network access and the public options response, or supply --options-file. No backend data was changed.')
    process.exitCode = 1
  })
}
