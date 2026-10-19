import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import AppearanceControls from './AppearanceControls'

import { navigation, primaryNavigation, secondaryNavigation, isNavigationActive } from '../../services/publicNavigation'

const logoSrc = 'https://lh3.googleusercontent.com/aida-public/AB6AXuDCGXJAzZ-UcWviePlSOQS31EaODKnU6pYnNVPZAIb_b-9lqS8LhiVGxnepujEXC4rbBB7dpPXi16s19Sdppz9cRMR-W6-5qoOvKHiyjSLG90SoGGcrEUpx4Z5RaWE6rdOWa_BsxPa57V9ULj-cq7v2VYn_NFMd7eHZVxCDZISlBx1os-S3z_3e7nhljVT48l6trWf8o2hKb0Xdd7Jp-2sNGkPBc-SPgyiJhCh1VyCyCxGmv53SBGIj-DCzsF4BNKzvzA'

function BrandLogo() {
  return <span className="brand-lockup"><img src={logoSrc} alt="Da'wãnã Islamic Foundation" /><span><strong>Da&apos;wãnã</strong><small>ISLAMIC FOUNDATION</small></span></span>
}

let activeScrollFrame = null

function scrollToHashTarget(hash) {
  const target = document.getElementById(hash.replace(/^#/, ''))
  if (!target) return

  const header = document.querySelector('.watchword-bar')
  const navbar = document.querySelector('.navbar')
  const offset = (header?.getBoundingClientRect().height || 0) + (navbar?.getBoundingClientRect().height || 0) + 12
  const start = window.scrollY
  const destination = Math.max(0, target.getBoundingClientRect().top + start - offset)
  const distance = destination - start
  if (Math.abs(distance) < 2) return

  if (activeScrollFrame !== null) window.cancelAnimationFrame(activeScrollFrame)
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    window.scrollTo(0, destination)
    return
  }

  const isMobile = window.matchMedia('(max-width: 1100px)').matches
  const duration = Math.min(isMobile ? 1080 : 940, Math.max(isMobile ? 740 : 640, 520 + Math.abs(distance) * 0.24))
  const startedAt = performance.now()
  const animate = (now) => {
    const progress = Math.min((now - startedAt) / duration, 1)
    const eased = 1 - (1 - progress) ** 3
    window.scrollTo(0, start + distance * eased)
    if (progress < 1) activeScrollFrame = window.requestAnimationFrame(animate)
    else activeScrollFrame = null
  }
  activeScrollFrame = window.requestAnimationFrame(animate)
}

export function Container({ children, className = '' }) {
  return <div className={`container ${className}`}>{children}</div>
}

export function Navbar() {
  const [open, setOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [compact, setCompact] = useState(true)
  const compactRef = useRef(true)
  const headerRef = useRef(null)
  const moreRef = useRef(null)
  const moreButtonRef = useRef(null)
  const navigate = useNavigate()
  const location = useLocation()
  const navigationTimer = useRef(null)

  useLayoutEffect(() => {
    const header = headerRef.current
    const row = header.querySelector('.nav-inner')
    const brand = row.querySelector('.brand')
    const links = row.querySelector('.desktop-nav')
    const toggle = row.querySelector('.appearance-controls')
    const donate = row.querySelector('.nav-donate')
    let disposed = false
    const update = () => {
      if (disposed) return
      const gap = parseFloat(getComputedStyle(row).columnGap) || 0
      const actionGap = parseFloat(getComputedStyle(toggle.parentElement).columnGap) || 0
      const needed = brand.getBoundingClientRect().width + links.getBoundingClientRect().width
        + toggle.getBoundingClientRect().width + donate.getBoundingClientRect().width + actionGap + gap * 2
      const next = window.matchMedia('(max-width: 700px)').matches || needed + 8 > row.clientWidth
      if (compactRef.current !== next) {
        compactRef.current = next
        setOpen(false)
        setMoreOpen(false)
        setCompact(next)
      }
    }
    const observer = new ResizeObserver(update)
    ;[row, brand, links, toggle, donate].forEach((element) => observer.observe(element))
    window.addEventListener('resize', update)
    document.fonts?.ready.then(update)
    update()
    return () => { disposed = true; observer.disconnect(); window.removeEventListener('resize', update) }
  }, [])

  useEffect(() => {
    if (!moreOpen) return undefined
    const outside = (event) => { if (!moreRef.current?.contains(event.target)) setMoreOpen(false) }
    const escape = (event) => {
      if (event.key === 'Escape') { setMoreOpen(false); moreButtonRef.current?.focus() }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [moreOpen])

  useEffect(() => {
    const navbar = document.querySelector('.navbar')
    const update = () => document.documentElement.style.setProperty('--nav-bottom', `${navbar.getBoundingClientRect().bottom}px`)
    const observer = new ResizeObserver(update)
    observer.observe(navbar)
    window.addEventListener('scroll', update, { passive: true })
    update()
    return () => { observer.disconnect(); window.removeEventListener('scroll', update) }
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') { setOpen(false); document.querySelector('.menu-button')?.focus() }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [open])

  useEffect(() => () => window.clearTimeout(navigationTimer.current), [])

  function closeAndNavigate(event, href) {
    event.preventDefault()
    window.clearTimeout(navigationTimer.current)
    setOpen(false)
    setMoreOpen(false)
    navigationTimer.current = window.setTimeout(() => {
      if (href.startsWith('/#') && location.pathname === '/' && location.hash === href.slice(1)) {
        scrollToHashTarget(href.slice(href.indexOf('#') + 1))
      } else {
        navigate(href)
      }
    }, 220)
  }

  function goToHash(event, href) {
    setOpen(false)
    setMoreOpen(false)
    event.preventDefault()
    if (location.pathname === '/' && location.hash === href.slice(1)) {
      scrollToHashTarget(href.slice(href.indexOf('#') + 1))
      return
    }
    navigate(href)
  }

  function navigationLink([label, href]) {
    const active = isNavigationActive(href, location)
    return <Link key={href} to={href} className={active ? 'active' : undefined} aria-current={active ? 'page' : undefined} onClick={(event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      if (moreRef.current?.contains(event.currentTarget)) moreButtonRef.current?.focus()
      if (href.startsWith('/#')) goToHash(event, href)
      else { setOpen(false); setMoreOpen(false) }
    }}>{label}</Link>
  }

  return (
    <>
      <div className="watchword-bar">
        <Container className="watchword-inner">
          <div className="ticker-identity"><i /> <span>Da&apos;wãnã Islamic Foundation</span><b>•</b><em>Established 1994 · Formerly The Islamic Front</em></div>
          <div className="watchword-copy">
            <span className="arabic" lang="ar" dir="rtl">رِضْوَانُ اللهِ أَكْبَرُ</span>
            <b>•</b><span className="watchword-english">&quot;Allah&apos;s Pleasure is the greatest&quot;</span>
          </div>
        </Container>
      </div>
      <header className="navbar" ref={headerRef} data-compact={compact}>
        <Container className="nav-inner">
          <Link className="brand" to="/" onClick={() => setOpen(false)}>
            <BrandLogo />
          </Link>
          <nav className="desktop-nav" aria-label="Primary navigation" inert={compact}>
            {primaryNavigation.map(navigationLink)}
            <div className="nav-more" ref={moreRef} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setMoreOpen(false) }}>
              <button ref={moreButtonRef} type="button" className={`nav-more-button${secondaryNavigation.some(([, href]) => isNavigationActive(href, location)) ? ' active' : ''}`} aria-expanded={moreOpen} aria-controls="secondary-navigation" onClick={() => setMoreOpen((current) => !current)}>More <span aria-hidden="true">&#8964;</span></button>
              <div id="secondary-navigation" className="nav-more-links" hidden={!moreOpen}>{secondaryNavigation.map(navigationLink)}</div>
            </div>
          </nav>
          <div className="nav-actions">
            <AppearanceControls />
            <Link className="button button-small nav-donate" to="/donate">Donate</Link>
            <button className="menu-button" type="button" aria-label={open ? 'Close navigation' : 'Open navigation'} aria-controls="mobile-navigation" aria-expanded={open} onClick={() => { window.clearTimeout(navigationTimer.current); setOpen((current) => !current) }}><span /><span /><span /></button>
          </div>
        </Container>
      </header>
      <button className={`mobile-menu-backdrop ${open ? 'is-visible' : ''}`} type="button" aria-label="Close navigation" aria-hidden="true" tabIndex={-1} onClick={() => setOpen(false)} />
      <nav id="mobile-navigation" className={`mobile-nav ${open ? 'is-open' : ''}`} aria-label="Mobile navigation" aria-hidden={!open}>
        <div className="mobile-nav-heading"><span className="mobile-nav-label">Explore Da&apos;w&#227;n&#227;</span><span>ISLAMIC FOUNDATION</span></div>
        <div className="mobile-nav-links">{navigation.map(([label, href], index) => href.startsWith('/#') ? <a key={label} href={href} className={isNavigationActive(href, location) ? 'active' : undefined} aria-current={isNavigationActive(href, location) ? 'page' : undefined} style={{ '--menu-index': index }} onClick={(event) => closeAndNavigate(event, href)}>{label}<span aria-hidden="true">↗</span></a> : <Link key={label} to={href} style={{ '--menu-index': index }} className={isNavigationActive(href, location) ? 'active' : undefined} aria-current={isNavigationActive(href, location) ? 'page' : undefined} onClick={(event) => closeAndNavigate(event, href)}>{label}<span aria-hidden="true">↗</span></Link>)}</div>
        <div className="mobile-menu-actions"><Link className="button button-gold" to="/donate" onClick={(event) => closeAndNavigate(event, '/donate')}>Donate <span aria-hidden="true">↗</span></Link></div>
        <div className="mobile-nav-footer"><span className="mobile-nav-mark">✦</span><span>Knowledge · Faith · Service · Community</span></div>
      </nav>
    </>
  )
}

export function Footer() {
  return <footer className="footer"><Container><div className="footer-grid"><div><Link className="brand footer-brand" to="/"><BrandLogo /></Link><p>Promoting Islamic knowledge, spiritual development and community wellbeing.</p><span className="footer-arabic arabic">رِضْوَانُ اللهِ أَكْبَرُ</span></div><div><h3>Explore</h3><Link to="/#who-we-are">About</Link><Link to="/programs">Programs</Link><Link to="/events">Events</Link><Link to="/projects">Projects</Link><Link to="/dic">DIC</Link></div><div><h3>Engagement</h3><Link to="/media">Media &amp; Knowledge Library</Link><Link to="/get-involved">Get Involved</Link><Link to="/contact">Contact</Link><span className="muted">Official social channels TBA</span></div><div><h3>Support</h3><Link to="/donate">Donate</Link><Link to="/faq">FAQ</Link><span>Privacy Policy</span><span>Terms of Use</span></div></div><div className="footer-bottom"><span>© {new Date().getFullYear()} Da&apos;wãnã Islamic Foundation</span><span>Knowledge · Faith · Service · Community</span></div></Container></footer>
}

export function Layout({ children }) {
  const location = useLocation()

  useEffect(() => {
    const previousRestoration = window.history.scrollRestoration
    window.history.scrollRestoration = 'manual'
    return () => { window.history.scrollRestoration = previousRestoration }
  }, [])

  useLayoutEffect(() => {
    // Hash destinations retain the shared smooth section-navigation behavior.
    if (!location.hash) window.scrollTo(0, 0)
  }, [location.pathname, location.hash])

  useEffect(() => {
    const scrollToHash = () => {
      const hash = window.location.hash
      if (!hash) return
      window.requestAnimationFrame(() => scrollToHashTarget(hash))
    }
    window.addEventListener('hashchange', scrollToHash)
    scrollToHash()
    return () => window.removeEventListener('hashchange', scrollToHash)
  }, [location.hash, location.pathname])

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return

    const revealSelectors = [
      'main section:not(.hero)',
      '.hero-art',
      '.hero-copy > p',
      '.hero-actions > *',
      '.hero-meta > *',
      '.area-grid .area-card',
      '.media-grid .media-card',
      '.involved-grid .involved-card',
      '.catalog-grid .catalog-card',
      '.dic-area-grid > article',
      '.dic-process-grid > article',
      '.participant-card',
      '.summary-box',
      '.checkout-box',
      '.confirmation-box',
      '.footer-grid > div',
    ]
    const targets = [...document.querySelectorAll(revealSelectors.join(','))]
    const staggeredSelectors = new Set([
      '.hero-actions > *', '.hero-meta > *', '.area-grid .area-card',
      '.media-grid .media-card', '.involved-grid .involved-card',
      '.catalog-grid .catalog-card', '.dic-area-grid > article', '.dic-process-grid > article',
      '.footer-grid > div',
    ])

    targets.forEach((target) => {
      const groupSelector = [...staggeredSelectors].find((selector) => target.matches(selector))
      if (groupSelector) {
        const siblings = [...target.parentElement.querySelectorAll(`:scope > ${groupSelector.split(' ').at(-1)}`)]
        target.style.setProperty('--reveal-delay', `${Math.min(siblings.indexOf(target), 5) * 55}ms`)
      }
      target.classList.add('motion-ready')
    })

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return
        entry.target.dataset.visible = 'true'
        observer.unobserve(entry.target)
      })
    }, { rootMargin: '0px 0px 14% 0px', threshold: 0.08 })

    targets.forEach((target) => observer.observe(target))
    return () => observer.disconnect()
  }, [location.key])

  return <><Navbar /><main>{children}</main><Footer /></>
}
