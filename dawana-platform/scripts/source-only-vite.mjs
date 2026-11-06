// Preload for source-only tests: prevent every test-created Vite server from
// reading dotenv files or scanning dependencies. Run from dawana-platform.
import { registerHooks } from 'node:module'

registerHooks({
  load(url, context, nextLoad) {
    const result = nextLoad(url, context)
    if (url.includes('/src/services/') && url.endsWith('.test.js') && result.source) {
      return { ...result, source: result.source.toString().replaceAll(
        'createServer({', 'createServer({ envDir: false, optimizeDeps: { noDiscovery: true, include: [] },') }
    }
    return result
  },
})
