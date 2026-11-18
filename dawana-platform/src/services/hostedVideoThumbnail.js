/** Provider-derived display-only thumbnail; never trust an arbitrary remote image URL.
 * Only canonical approved YouTube playback URLs can form a known YouTube thumbnail.
 * Vimeo has no deterministic public poster URL; retain the accessible play fallback.
 */
export function hostedVideoThumbnail(embed) {
  try {
    const url = new URL(embed)
    if (url.protocol !== 'https:' || url.hostname !== 'www.youtube-nocookie.com' ||
        url.username || url.password || url.port || url.hash ||
        url.search !== '?playsinline=1') return ''
    const match = /^\/embed\/([A-Za-z0-9_-]{11})$/.exec(url.pathname)
    return match ? 'https://i.ytimg.com/vi/' + match[1] + '/hqdefault.jpg' : ''
  } catch { return '' }
}
