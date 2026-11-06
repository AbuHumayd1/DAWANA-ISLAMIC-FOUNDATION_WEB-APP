// Only application API URLs, never bucket endpoints or arbitrary remote hosts.
export function resolveMediaUrl(value, apiBase = import.meta.env?.VITE_API_BASE_URL || '/api/v1') {
  if (typeof value !== 'string' || !value || /[\\\s]/.test(value) ||
      [...value].some(char => char.charCodeAt(0) < 32) || value.startsWith('//')) return ''
  try {
    const relative = !/^https?:\/\//.test(apiBase)
    const origin = 'https://relative.invalid'
    const base = new URL(apiBase.replace(/\/+$/, '') + '/', origin)
    const url = new URL(value, base)
    const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
    if (url.origin !== base.origin || url.username || url.password ||
        (url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) ||
        !url.pathname.startsWith(base.pathname)) return ''
    return relative ? url.pathname + url.search + url.hash : url.href
  } catch { return '' }
}
