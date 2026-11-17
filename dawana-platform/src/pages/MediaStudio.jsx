import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { studioSession, studioLogin, studioLogout, studioLibrary, studioPublish } from '../services/mediaStudioApi'
import './MediaStudio.css'

const LIBRARIES = [
  { key: 'photos', name: 'Photography', count: 'Photographs & memories', icon: '📷' },
  { key: 'videos', name: 'Videos', count: 'Camp videos & footage', icon: '▸' },
  { key: 'recordings', name: 'Audio recordings', count: 'Lectures & learning', icon: '🎙' },
  { key: 'flyers', name: 'Flyers & artwork', count: 'Official visual campaigns', icon: '▧' },
  { key: 'promotions', name: 'Promotions', count: 'Video campaigns', icon: '✦' },
  { key: 'lecturers', name: 'Lecturers', count: 'Profiles & expertise', icon: '♙' },
  { key: 'appearances', name: 'Appearances', count: 'Speaker programmes', icon: '◫' },
  { key: 'activities', name: 'Activities', count: 'Events & highlights', icon: '▤' },
]

export default function MediaStudio() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [message, setMessage] = useState('')
  const [loginBusy, setLoginBusy] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [library, setLibrary] = useState('photos')
  const [q, setQ] = useState('')
  const [state, setState] = useState('')
  const [edition, setEdition] = useState('')
  const [rows, setRows] = useState([])
  const [canPublish, setCanPublish] = useState(false)
  const [loading, setLoading] = useState(false)
  const [more, setMore] = useState(false)
  const [pending, setPending] = useState(null)
  const menuRef = useRef(null)
  const seq = useRef(0)
  useEffect(() => {
    let mounted = true
    studioSession().then(v => { if (mounted) setUser(v) })
      .catch(() => {}).finally(() => { if (mounted) setChecking(false) })
    return () => { mounted = false }
  }, [])
  useEffect(() => {
    if (!menuOpen) return
    function outside(event) { if (!menuRef.current?.contains(event.target)) setMenuOpen(false) }
    function escape(event) { if (event.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [menuOpen])
  useEffect(() => {
    if (!user) return
    if (!user.libraries?.includes(library)) {
      setLibrary(user.libraries?.[0] || 'photos')
      return
    }
    let active = true
    const current = ++seq.current
    setLoading(true); setMessage('')
    studioLibrary({ library, q, state, edition })
      .then(data => { if (active && current === seq.current) { setRows(data.items); setMore(data.has_more); setCanPublish(data.can_publish) } })
      .catch(e => { if (active && current === seq.current) { setRows([]); setMessage(e.message) } })
      .finally(() => { if (active && current === seq.current) setLoading(false) })
    return () => { active = false }
  }, [user, library, q, state, edition])
  async function signIn(event) {
    event.preventDefault(); setLoginBusy(true); setMessage('')
    const form = new FormData(event.currentTarget)
    try { setUser(await studioLogin(form.get('username'), form.get('password'))) }
    catch (error) { setMessage(error.message) }
    finally { setLoginBusy(false) }
  }
  async function signOut() {
    try { await studioLogout(); setUser(null); setRows([]); setMenuOpen(false) }
    catch (error) { setMessage(error.message) }
  }
  async function publish(item, action) {
    setPending(item.id); setMessage('')
    try {
      const result = await studioPublish(library, item.id, action)
      setRows(previous => previous.map(row => row.id === item.id ? { ...row, state: result.state } : row))
      setMessage(`${item.title} — ${action === 'publish' ? 'published' : 'withdrawn'}.`)
    } catch (error) { setMessage(error.message) }
    finally { setPending(null) }
  }
  if (checking) return <main className="studio-checking" aria-busy="true">Opening the secure DAWANA Media Studio…</main>
  if (!user) return <main className="studio-login"><Link to="/" className="studio-back">← DAWANA Islamic Foundation</Link><section className="studio-login-card">
    <span className="studio-kicker">THE CREATIVE WORKSPACE</span>
    <h1>Every story deserves a beautiful home.</h1>
    <p>DAWANA Media Studio — a private workspace for our Foundation media team.</p>
    <form onSubmit={signIn}><label>Staff username or email<input name="username" autoComplete="username" required maxLength="150" /></label>
    <label>Password<input type="password" name="password" autoComplete="current-password" required /></label>
    {message && <p role="alert" className="studio-error">{message}</p>}
    <button type="submit" disabled={loginBusy}>{loginBusy ? 'Signing in…' : 'Enter Media Studio'} <span aria-hidden="true">→</span></button></form>
    <small>Authorized personnel only. Your existing DAWANA staff credentials are used.</small>
  </section></main>

  const selected = LIBRARIES.find(x => x.key === library)
  return <div className="studio-app">
    <header className="studio-top"><div className="studio-nav-wrapper" ref={menuRef}><button className="studio-hamburger" aria-label="Toggle Studio navigation" aria-expanded={menuOpen} aria-controls="studio-menu" onClick={() => setMenuOpen(value => !value)}>☰</button>
      {menuOpen && <nav id="studio-menu" className="studio-popnav" aria-label="Media Studio sections">
        <strong>Media collections</strong>
        {LIBRARIES.filter(x => user.libraries?.includes(x.key)).map(x => <button type="button" key={x.key} onClick={() => { setLibrary(x.key); setQ(''); setState(''); setEdition(''); setMenuOpen(false) }} aria-current={library === x.key ? 'page' : undefined}><span>{x.icon}</span>{x.name}</button>)}
      </nav>}</div>
      <Link to="/" className="studio-logo"><img src="/dawana-official-logo.png" alt="" /><span><strong>DAWANA</strong><small>MEDIA STUDIO</small></span></Link>
      <div className="studio-account"><span className="studio-identity">{user.display_name}{user.owner ? <small>System administrator</small> : <small>Media team</small>}</span><button type="button" onClick={signOut}>Sign out</button></div>
    </header>
    <main className="studio-main">
      <div className="studio-overview"><div><span className="studio-kicker">CREATIVE COMMAND CENTRE</span><h1>Capture. Curate. Share.</h1><p>One place for DAWANA's stories, lectures and memorable moments.</p></div><div className="studio-overview-mark" aria-hidden="true">✦</div></div>
      <section className="studio-collections" aria-label="Media collections"><h2>Explore collections</h2><div className="studio-collection-grid">{LIBRARIES.filter(x => user.libraries?.includes(x.key)).map(x => <button key={x.key} type="button" className={'studio-collection' + (library === x.key ? ' active' : '')} onClick={() => { setLibrary(x.key); setQ(''); setState(''); setEdition('') }}><span className="studio-collection-icon">{x.icon}</span><strong>{x.name}</strong><small>{x.count}</small></button>)}</div></section>
      <section className="studio-workspace" aria-labelledby="studio-library-title">
        <div className="studio-heading"><div><span className="studio-kicker">THE LIBRARY</span><h2 id="studio-library-title">{selected?.name}</h2><p>Browse and manage existing media securely. No file is publicly released until published.</p></div><span className="studio-library-meta">Showing up to 100 items</span></div>
        <div className="studio-filters"><label>Search<input aria-label="Search media" placeholder="Search titles and captions" value={q} onChange={e => setQ(e.target.value)} /></label>
          <label>Publication status<select aria-label="Filter publication status" value={state} onChange={e => setState(e.target.value)}><option value="">All statuses</option><option value="draft">Draft</option><option value="review">Review</option><option value="published">Published</option></select></label>
          {!['lecturers'].includes(library) && <label>Camp edition ID<input aria-label="Filter edition" inputMode="numeric" placeholder="All editions" value={edition} onChange={e => setEdition(e.target.value.replace(/[^0-9]/g,''))}/></label>}
        </div>
        {message && <p className="studio-notice" role="status">{message}</p>}
        {loading ? <p className="studio-state">Loading media catalogue…</p> : rows.length ? <div className="studio-item-grid">{rows.map(item => <article className="studio-item" key={item.id}>
          <div className="studio-art"><span aria-hidden="true">{selected?.icon}</span><small>Asset #{item.id}</small></div>
          <div className="studio-item-body"><div className="studio-item-meta"><span className={'studio-status studio-status-' + item.state}>{item.state}</span>{item.edition && <span>Edition {item.edition}</span>}</div><h3>{item.title}</h3><div className="studio-item-actions">{canPublish && ['photos','videos','recordings','flyers','promotions','activities'].includes(library) ? <button type="button" disabled={pending !== null} onClick={() => publish(item, item.state === 'published' ? 'withdraw' : 'publish')}>{pending === item.id ? 'Saving…' : item.state === 'published' ? 'Withdraw' : 'Publish'}</button> : <span>Read-only catalogue</span>}</div></div>
        </article>)}</div> : <div className="studio-state"><strong>No media records match this view.</strong><p>Use the filters to find existing items. New uploads and the full unified media composer will be enabled after private storage activation and validation.</p></div>}
        {more && <p className="studio-pagination">More than 100 items match this view. Narrow your search to see more specific results.</p>}
      </section>
      <aside className="studio-storage-note"><strong>Publishing and private storage</strong><p>All library records and publishing actions are authorized by the backend. Private R2 activation and new uploads remain disabled until the owner approves the production storage cutover.</p></aside>
    </main>
  </div>
}
