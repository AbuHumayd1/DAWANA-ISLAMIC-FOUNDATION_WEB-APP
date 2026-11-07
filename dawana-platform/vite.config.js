import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'
import { productionApiBase } from './src/services/productionContract.js'

// https://vite.dev/config/
export default defineConfig(({ command, mode }) => {
  if (command === 'build' && mode === 'production') {
    const env = loadEnv(mode, process.cwd(), 'VITE_')
    productionApiBase(process.env.VITE_API_BASE_URL ?? env.VITE_API_BASE_URL ?? '/api/v1')
  }
  return {
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/static': {
        target: process.env.DJANGO_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/admin': {
        target: process.env.DJANGO_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/api': {
        target: process.env.DJANGO_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  }
})
