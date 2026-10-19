export function stagingRedirects(env) {
  if (env.DAWANA_STAGING_FRONTEND !== 'true' || !env.SITE_ID || env.SITE_ID !== env.DAWANA_STAGING_SITE_ID) {
    throw new Error('Use only a separately approved staging Netlify site with matching staging site ID.')
  }
  const origin = new URL(env.STAGING_BACKEND_ORIGIN)
  if (origin.protocol !== 'https:' || !origin.hostname.endsWith('.onrender.com') || origin.username || origin.password || origin.port || origin.pathname !== '/' || origin.search || origin.hash) {
    throw new Error('Use the HTTPS origin of the approved Render staging service, without a path.')
  }
  if (env.VITE_API_BASE_URL && env.VITE_API_BASE_URL !== '/api/v1') {
    throw new Error('The staging proxy requires VITE_API_BASE_URL=/api/v1 to preserve cookie authentication.')
  }
  return ['/api/', '/admin/', '/static/'].map((path) => `${path}* ${origin.origin}${path}:splat 200!`).join('\n') + '\n/* /index.html 200\n'
}
