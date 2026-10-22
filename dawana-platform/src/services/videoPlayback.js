export function safeVideoEmbed(source) {
  try {
    const url = new URL(source.embed_url)
    if (url.protocol !== 'https:' || url.username || url.password || url.port || url.hash) return null
    if (source.provider === 'youtube' && url.hostname === 'www.youtube-nocookie.com' && /^\/embed\/[A-Za-z0-9_-]{11}$/.test(url.pathname) && url.search === '?playsinline=1') return url.href
    if (source.provider === 'vimeo' && url.hostname === 'player.vimeo.com' && /^\/video\/[1-9][0-9]{0,11}$/.test(url.pathname) && url.search === '?dnt=1') return url.href
  } catch { /* Fail closed for malformed playback responses. */ }
  return null
}
