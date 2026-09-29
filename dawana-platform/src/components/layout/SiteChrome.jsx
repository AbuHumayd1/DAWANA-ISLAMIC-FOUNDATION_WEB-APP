import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useLayoutEffect, useState } from 'react'

const navigation = [
  ['Home', '/'],
  ['About', '/about'],
  ['What We Do', '/#what-we-do'],
  ['Programs', '/programs'],
  ['Events', '/events'],
  ['Projects', '/projects'],
  ['DIC', '/dic'],
  ['Media', '/media'],
  ['Get Involved', '/get-involved'],
]

const logoSrc = 'https://lh3.googleusercontent.com/aida-public/AB6AXuDCGXJAzZ-UcWviePlSOQS31EaODKnU6pYnNVPZAIb_b-9lqS8LhiVGxnepujEXC4rbBB7dpPXi16s19Sdppz9cRMR-W6-5qoOvKHiyjSLG90SoGGcrEUpx4Z5RaWE6rdOWa_BsxPa57V9ULj-cq7v2VYn_NFMd7eHZVxCDZISlBx1os-S3z_3e7nhljVT48l6trWf8o2hKb0Xdd7Jp-2sNGkPBc-SPgyiJhCh1VyCyCxGmv53SBGIj-DCzsF4BNKzvzA'

function BrandLogo() {
  return <span className="brand-lockup"><img src={logoSrc} alt="Da'wãnã Islamic Foundation" /><span><strong>Da&apos;wãnã</strong><small>ISLAMIC FOUNDATION</small></span></span>
}

function scrollToHashTarget(hash) {
  window.setTimeout(() => {
    const target = document.getElementById(hash.replace(/^#/, ''))
    if (!target) return
    const header = document.querySelector('.watchword-bar')
    const navbar = document.querySelector('.navbar')
    const offset = (header?.getBoundingClientRect().height || 0) + (navbar?.getBoundingClientRect().height || 0) + 10
    window.scrollTo({ top: target.getBoundingClientRect().top + window.scrollY - offset, behavior: 'smooth' })
  }, 50)
}

export function Container({ children, className = '' }) {
  return <div className={`container ${className}`}>{children}</div>
}

export function Navbar() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  function goToHash(event, href) {
    setOpen(false)
    if (location.pathname === '/') {
      return
    }
    event.preventDefault()
    navigate(href)
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
      <header className="navbar">
        <Container className="nav-inner">
          <Link className="brand" to="/" onClick={() => setOpen(false)}>
            <BrandLogo />
          </Link>
          <nav className="desktop-nav" aria-label="Primary navigation">
            {navigation.map(([label, href]) => href.startsWith('/#') ? <a key={label} href={href} onClick={(event) => goToHash(event, href)}>{label}</a> : <NavLink key={label} to={href} className={({ isActive }) => isActive ? 'active' : undefined}>{label}</NavLink>)}
          </nav>
          <div className="nav-actions">
            <Link className="login-link" to="/login">Login</Link>
            <Link className="button button-small" to="/donate">Donate</Link>
            <button className="menu-button" type="button" aria-label="Toggle navigation" aria-expanded={open} onClick={() => setOpen(!open)}><span /><span /><span /></button>
          </div>
        </Container>
        {open && <nav className="mobile-nav" aria-label="Mobile navigation"><span className="mobile-nav-label">Navigation</span>{navigation.map(([label, href]) => href.startsWith('/#') ? <a key={label} href={href} onClick={(event) => goToHash(event, href)}>{label}</a> : <NavLink key={label} to={href} className={({ isActive }) => isActive ? 'active' : undefined} onClick={() => setOpen(false)}>{label}</NavLink>)}<Link className="mobile-login" to="/login" onClick={() => setOpen(false)}>Login</Link><Link className="button button-gold" to="/donate" onClick={() => setOpen(false)}>Donate</Link></nav>}
      </header>
    </>
  )
}

export function Footer() {
  return <footer className="footer"><Container><div className="footer-grid"><div><Link className="brand footer-brand" to="/"><BrandLogo /></Link><p>Promoting Islamic knowledge, spiritual development and community wellbeing.</p><span className="footer-arabic arabic">رِضْوَانُ اللهِ أَكْبَرُ</span></div><div><h3>Explore</h3><Link to="/about">About</Link><Link to="/programs">Programs</Link><Link to="/events">Events</Link><Link to="/projects">Projects</Link><Link to="/dic">DIC</Link></div><div><h3>Engagement</h3><Link to="/media">Media &amp; Knowledge Library</Link><Link to="/get-involved">Get Involved</Link><Link to="/contact">Contact</Link><span className="muted">Official social channels TBA</span></div><div><h3>Support</h3><Link to="/donate">Donate</Link><Link to="/faq">FAQ</Link><span>Privacy Policy</span><span>Terms of Use</span></div></div><div className="footer-bottom"><span>© {new Date().getFullYear()} Da&apos;wãnã Islamic Foundation</span><span>Knowledge · Faith · Service · Community</span></div></Container></footer>
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
      window.setTimeout(() => {
        scrollToHashTarget(hash)
      }, 100)
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
