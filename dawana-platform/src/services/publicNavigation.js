export const primaryNavigation = [
  ['Home', '/'], ['About', '/#who-we-are'], ['Programs', '/programs'],
  ['Events', '/events'], ['DIC', '/dic'],
]
export const secondaryNavigation = [
  ['What We Do', '/#what-we-do'], ['Projects', '/projects'],
  ['Participant portal', '/dic/participant'], ['Media', '/media'],
  ['Contact', '/contact'], ['Get Involved', '/get-involved'], ['FAQ', '/faq'],
]
export const navigation = [...primaryNavigation, ...secondaryNavigation]

export function isNavigationActive(href, { pathname, hash }) {
  if (href.includes('#')) return pathname === '/' && hash === href.slice(1)
  if (href === '/') return pathname === '/' && !hash
  if (href === '/dic' && pathname.startsWith('/dic/participant')) return false
  return pathname === href || pathname.startsWith(`${href}/`)
}
