// OWNER-RUN ONLY. Isolated asset build: no dotenv, application server or provider.
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createRequire } from 'node:module'
const root = fileURLToPath(new URL('../', import.meta.url))
const frontend = path.join(root, 'dawana-platform')
const require = createRequire(path.join(frontend, 'package.json'))
const { build } = await import(pathToFileURL(require.resolve('vite')))
const react = (await import(pathToFileURL(require.resolve('@vitejs/plugin-react')))).default
const tailwindcss = (await import(pathToFileURL(require.resolve('@tailwindcss/vite')))).default
await build({ root: frontend, configFile: false, envDir: false, mode: 'production',
  plugins: [react(), tailwindcss()],
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api/v1') },
  build: { outDir: path.join(root, 'output/historical-recovery-sprint/operations-production-build'), emptyOutDir: false } })
