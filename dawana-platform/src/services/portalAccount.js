// Callback hints are never authority; /auth/me/ authenticates the session.
export function oauthReturn(hash) {
  return hash === '#signin=complete' || hash === '#signin=failed'
}

export function googleAuthorizationUrl(value) {
  const url = new URL(value)
  if (url.origin !== 'https://accounts.google.com' || url.pathname !== '/o/oauth2/v2/auth' || url.username || url.password || url.hash) throw new Error('Invalid Google authorization destination.')
  if (url.searchParams.get('response_type') !== 'code' || url.searchParams.get('code_challenge_method') !== 'S256') throw new Error('Invalid Google authorization flow.')
  return url.href
}
