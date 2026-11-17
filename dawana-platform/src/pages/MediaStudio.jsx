import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { backendUrl } from '../services/productionContract'
import { studioSession, studioLogin, studioLogout, studioLibrary, studioPublish, studioUpload, studioUploadStatus, studioEdit, studioLinkAsset, studioHostedLinks } from '../services/mediaStudioApi'
import './MediaStudio.css'
import StudioDestinations from './StudioDestinations'

const COMPOSER_FIELDS = {
  photos: [{ name: 'caption', label: 'Caption', required: true }, { name: 'alt_text', label: 'Accessible description', required: true }, { name: 'photograph', label: 'Photograph', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }],
  videos: [{ name: 'caption', label: 'Title / caption', required: true }, { name: 'alt_text', label: 'Thumbnail description', required: true }, { name: 'lecturer', label: 'Lecturer (optional)' }, { name: 'thumbnail', label: 'Thumbnail', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }, { name: 'recording_file', label: 'Video recording', file: true, accept: 'video/mp4,video/webm', required: true }],
  recordings: [{ name: 'title', label: 'Recording title', required: true }, { name: 'lecturer', label: 'Lecturer' }, { name: 'description', label: 'Description' }, { name: 'audio', label: 'Audio recording', file: true, accept: 'audio/mpeg,audio/mp4,audio/wav,audio/ogg', required: true }],
  flyers: [{ name: 'title', label: 'Official flyer title', required: true }, { name: 'alt_text', label: 'Accessible description', required: true }, { name: 'image', label: 'Flyer artwork', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }],
  promotions: [{ name: 'title', label: 'Promotion title', required: true }, { name: 'description', label: 'Description' }, { name: 'alt_text', label: 'Poster description', required: true }, { name: 'poster', label: 'Poster', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }, { name: 'video', label: 'H.264/AAC MP4', file: true, accept: 'video/mp4', required: true }],
  lecturers: [{ name: 'name', label: 'Lecturer name', required: true }, { name: 'designation', label: 'Designation' }, { name: 'biography', label: 'Biography', required: true }, { name: 'alt_text', label: 'Portrait description', required: true }, { name: 'photograph', label: 'Lecturer portrait', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }],
  activities: [{ name: 'title', label: 'Activity title', required: true }, { name: 'category', label: 'Category', required: true }, { name: 'description', label: 'Description', required: true }, { name: 'alt_text', label: 'Photo description (if supplied)' }, { name: 'photograph', label: 'Optional activity photograph', file: true, accept: 'image/jpeg,image/png,image/webp' }],
}

const LIBRARIES = [
  { key: 'photos', name: 'Photography', count: 'Photographs & memories', icon: '📷' },
  { key: 'videos', name: 'Videos', count: 'Camp videos & footage', icon: '▸' },
  { key: 'hosted', name: 'YouTube & Live', count: 'Paste video and livestream links', icon: '▶' },
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
  const [page, setPage] = useState(1)
  const [canPublish, setCanPublish] = useState(false)
  const [canEdit, setCanEdit] = useState(false)
  const [canCreate, setCanCreate] = useState(false)
  const [hostedLinks, setHostedLinks] = useState('')
  const [hostedLecturer, setHostedLecturer] = useState('')
  const [hostedDescription, setHostedDescription] = useState('')
  const [hostedEdition, setHostedEdition] = useState('')
  const [editing, setEditing] = useState(null)
  const [preview, setPreview] = useState(null)
  const [focusAsset, setFocusAsset] = useState('')
  const [loading, setLoading] = useState(false)
  const [more, setMore] = useState(false)
  const [pending, setPending] = useState(null)
  const [uploadInfo, setUploadInfo] = useState({ enabled: false, editions: [], libraries: [] })
  const [composerOpen, setComposerOpen] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const menuRef = useRef(null)
  const seq = useRef(0)
  useEffect(() => {
    let mounted = true
    studioSession().then(v => { if (mounted) setUser(v) })
      .catch(() => {}).finally(() => { if (mounted) setChecking(false) })
    return () => { mounted = false }
  }, [])
  useEffect(() => {
    if (!user) return
    studioUploadStatus().then(setUploadInfo).catch(() => setUploadInfo({ enabled: false, editions: [], libraries: [] }))
  }, [user])
  useEffect(() => { setComposerOpen(false); setPreview(null); setEditing(null) }, [library])
  useEffect(() => {
    if (!preview) return undefined
    function closeOnEscape(event) { if (event.key === 'Escape') setPreview(null) }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [preview])
  function safePlayer(value) {
    try {
      const url = new URL(value)
      return url.protocol === 'https:' && ['www.youtube-nocookie.com', 'player.vimeo.com'].includes(url.hostname)
        && !url.username && !url.password && !url.hash && !url.port ? url.href : ''
    } catch { return '' }
  }
  async function addHostedLinks(event) {
    event.preventDefault()
    const lines = hostedLinks.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
    if (!lines.length || lines.length > 25) {
      setMessage('Provide between 1 and 25 YouTube/Vimeo links per batch.'); return
    }
    const entries = lines.map(line => {
      const separator = line.indexOf('|')
      return separator < 0 ? null : {
        title: line.slice(0, separator).trim(),
        video_url: line.slice(separator + 1).trim(),
        lecturer: hostedLecturer.trim(),
        description: hostedDescription.trim(),
        ...(hostedEdition ? { edition: hostedEdition } : {}),
      }
    })
    if (entries.some(entry => !entry?.title || !entry?.video_url)) {
      setMessage('Each line needs its title, a vertical bar (|), then the video URL.'); return
    }
    setUploadBusy(true); setMessage('')
    try {
      const response = await studioHostedLinks(entries)
      setHostedLinks('')
      setMessage(`${response.items.length} YouTube/Vimeo link${response.items.length === 1 ? '' : 's'} saved as private drafts. Publish their sources, then choose destinations below. No video files were uploaded.`)
      setRevision(n => n + 1)
      setComposerOpen(false)
    } catch (error) { setMessage(error.message) }
    finally { setUploadBusy(false) }
  }
  async function upload(event) {
    event.preventDefault()
    const form = event.currentTarget
    const formData = new FormData(form)
    const values = Object.fromEntries(formData)
    const photos = library === 'photos' ? formData.getAll('photograph').filter(file => file instanceof File && file.name && file.size) : []
    if (library === 'photos' && photos.length > 20) {
      setMessage('Select up to 20 photographs per batch.'); return
    }
    setUploadBusy(true); setMessage('')
    let saved = 0
    try {
      if (photos.length > 1) {
        for (const photo of photos) {
          await studioUpload(library, { ...values, photograph: photo })
          saved += 1
        }
      } else {
        await studioUpload(library, values)
        saved = 1
      }
      setMessage(`${saved} media item${saved === 1 ? '' : 's'} saved as private drafts. Review before publishing.`)
      setComposerOpen(false)
    } catch (error) { setMessage(saved ? `${saved} items saved; remaining uploads stopped: ${error.message}` : error.message) }
    finally {
      if (saved) setRevision(current => current + 1)
      setUploadBusy(false)
    }
  }
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
    studioLibrary({ library, q, state, edition, page })
      .then(data => { if (active && current === seq.current) { setRows(previous => page === 1 ? data.items : [...previous.filter(item => !data.items.some(next => next.id === item.id)), ...data.items]); setMore(data.has_more); setCanPublish(data.can_publish); setCanEdit(data.can_edit); setCanCreate(data.can_create) } })
      .catch(e => { if (active && current === seq.current) { setRows([]); setMessage(e.message) } })
      .finally(() => { if (active && current === seq.current) setLoading(false) })
    return () => { active = false }
  }, [user, library, q, state, edition, revision, page])
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
  async function addToFoundation(item) {
    setPending(item.id); setMessage('')
    try {
      const result = await studioLinkAsset(library, item.id)
      setFocusAsset(result.asset?.id || '')
      setRevision(current => current + 1)
      setMessage(result.created ? 'Media linked to the Foundation catalogue. Choose publication destinations below.' : 'Already linked to the Foundation catalogue. Manage destinations below.')
    } catch (error) { setMessage(error.message) }
    finally { setPending(null) }
  }
  async function saveMetadata(event, item) {
    event.preventDefault()
    setPending(item.id); setMessage('')
    const values = Object.fromEntries(new FormData(event.currentTarget))
    const metadata = {}
    for (const [key, original] of Object.entries(item.metadata || {})) {
      if (typeof original === 'boolean') metadata[key] = values[key] === 'on'
      else if (typeof original === 'number') metadata[key] = Number(values[key])
      else metadata[key] = values[key] || ''
    }
    try {
      const response = await studioEdit(library, item.id, metadata)
      setRows(previous => previous.map(row => row.id === item.id ? { ...row, metadata: response.metadata, state: response.state, title: response.metadata.title || response.metadata.name || response.metadata.caption || row.title } : row))
      setEditing(null)
      setMessage('Changes saved. Previously published material has been returned to draft for review.')
    } catch (error) { setMessage(error.message) }
    finally { setPending(null) }
  }
  async function publish(item, action) {
    setPending(item.id); setMessage('')
    try {
      const result = await studioPublish(library, item.id, action)
      setRows(previous => previous.map(row => row.id === item.id ? { ...row, state: result.state } : row))
      setRevision(current => current + 1)
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
  const publishedInView = rows.filter(item => item.state === 'published').length
  const draftsInView = rows.filter(item => item.state === 'draft').length
  return <div className="studio-app">
    <header className="studio-top"><div className="studio-nav-wrapper" ref={menuRef}><button className="studio-hamburger" aria-label="Toggle Studio navigation" aria-expanded={menuOpen} aria-controls="studio-menu" onClick={() => setMenuOpen(value => !value)}>☰</button>
      {menuOpen && <nav id="studio-menu" className="studio-popnav" aria-label="Media Studio sections">
        <strong>Media collections</strong>
        {LIBRARIES.filter(x => user.libraries?.includes(x.key)).map(x => <button type="button" key={x.key} onClick={() => { setPage(1); setLibrary(x.key); setQ(''); setState(''); setEdition(''); setMenuOpen(false) }} aria-current={library === x.key ? 'page' : undefined}><span>{x.icon}</span>{x.name}</button>)}
      </nav>}</div>
      <Link to="/" className="studio-logo"><img src="/dawana-official-logo.png" alt="" /><span><strong>DAWANA</strong><small>MEDIA STUDIO</small></span></Link>
      <div className="studio-account"><span className="studio-identity">{user.display_name}{user.owner ? <small>System administrator</small> : <small>Media team</small>}</span><button type="button" onClick={signOut}>Sign out</button></div>
    </header>
    <main className="studio-main">
      <div className="studio-overview"><div><span className="studio-kicker">CREATIVE COMMAND CENTRE</span><h1>Capture. Curate. Share.</h1><p>One place for DAWANA's stories, lectures and memorable moments.</p></div><div className="studio-overview-mark" aria-hidden="true">✦</div></div>
      <section className="studio-collections" aria-label="Media collections"><h2>Explore collections</h2><div className="studio-collection-grid">{LIBRARIES.filter(x => user.libraries?.includes(x.key)).map(x => <button key={x.key} type="button" className={'studio-collection' + (library === x.key ? ' active' : '')} onClick={() => { setPage(1); setLibrary(x.key); setQ(''); setState(''); setEdition('') }}><span className="studio-collection-icon">{x.icon}</span><strong>{x.name}</strong><small>{x.count}</small></button>)}</div></section>
      <section className="studio-workspace" aria-labelledby="studio-library-title">
        <div className="studio-heading"><div><span className="studio-kicker">THE LIBRARY</span><h2 id="studio-library-title">{selected?.name}</h2><p>Browse and manage existing media securely. No file is publicly released until published.</p></div><div className="studio-heading-actions"><span className="studio-library-meta">{rows.length} loaded · {publishedInView} published · {draftsInView} drafts</span>{library === 'hosted' && canCreate && <button className="studio-create" type="button" onClick={() => setComposerOpen(open => !open)}>{composerOpen ? 'Close links' : '+ Add YouTube links'}</button>}{uploadInfo.enabled && uploadInfo.libraries.includes(library) && <button className="studio-create" type="button" onClick={() => setComposerOpen(open => !open)}>{composerOpen ? 'Close upload' : '+ Add media'}</button>}</div></div>
        {library === 'hosted' && composerOpen && canCreate && <form className="studio-composer studio-hosted-composer" onSubmit={addHostedLinks}>
          <div><span className="studio-kicker">YOUTUBE · LIVESTREAMS · VIMEO</span><h3>Paste video links in bulk</h3><p>One per line: <strong>Video title | https://www.youtube.com/live/VIDEO_ID</strong>. Up to 25 links per batch. Stream URLs work during the broadcast and may remain available for replay, subject to YouTube settings. No file upload or R2 storage required.</p></div>
          <label className="studio-hosted-lines">Video titles and links<textarea required rows={6} value={hostedLinks} onChange={e => setHostedLinks(e.target.value)} placeholder={'Friday Lecture | https://www.youtube.com/watch?v=VIDEO_ID\nSpecial Programme | https://www.youtube.com/live/VIDEO_ID'} /></label>
          <label>Lecturer / presenter (optional)<input value={hostedLecturer} onChange={e => setHostedLecturer(e.target.value)} maxLength={200}/></label>
          <label>Camp edition (optional)<select value={hostedEdition} onChange={e => setHostedEdition(e.target.value)}><option value="">Foundation-wide</option>{uploadInfo.editions.map(item => <option key={item.id} value={item.id}>{item.name} ({item.year})</option>)}</select></label>
          <label className="studio-hosted-lines">Description for these entries (optional)<textarea rows={2} value={hostedDescription} onChange={e => setHostedDescription(e.target.value)} maxLength={5000}/></label>
          <button type="submit" disabled={uploadBusy}>{uploadBusy ? 'Validating links…' : 'Save links as drafts'}</button>
        </form>}
        {composerOpen && uploadInfo.enabled && <form className="studio-composer" onSubmit={upload} encType="multipart/form-data"><div><span className="studio-kicker">NEW MEDIA</span><h3>Create a private draft</h3><p>Publishing is a separate action. Uploaded objects remain private unless explicitly released.</p></div>
          {library !== 'lecturers' && <label>Edition<select name="edition" required defaultValue=""><option value="">Select camp edition</option>{uploadInfo.editions.map(item => <option key={item.id} value={item.id}>{item.name} ({item.year})</option>)}</select></label>}
          {library === 'promotions' && <><label>Promotion type<select required name="kind"><option value="introduction">Upcoming introduction</option><option value="experience">Previous participant experience</option></select></label><label>Previous source edition (for experience videos)<select name="source_edition" defaultValue=""><option value="">Not applicable</option>{uploadInfo.editions.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></>}
          {COMPOSER_FIELDS[library]?.map(field => <label key={field.name}>{field.label}<input name={field.name} type={field.file ? 'file' : 'text'} multiple={library === 'photos' && field.name === 'photograph'} accept={field.accept} required={field.required} maxLength={field.file ? undefined : 2000} /></label>)}
          <button type="submit" disabled={uploadBusy}>{uploadBusy ? 'Validating and uploading…' : 'Save private draft'}</button>
        </form>}
        <div className="studio-filters"><label>Search<input aria-label="Search media" placeholder="Search titles and captions" value={q} onChange={e => { setPage(1); setQ(e.target.value) }} /></label>
          <label>Publication status<select aria-label="Filter publication status" value={state} onChange={e => { setPage(1); setState(e.target.value) }}><option value="">All statuses</option><option value="draft">Draft</option>{library !== 'hosted' && <option value="review">Review</option>}<option value="published">Published</option></select></label>
          {!['lecturers'].includes(library) && <label>Camp edition ID<input aria-label="Filter edition" inputMode="numeric" placeholder="All editions" value={edition} onChange={e => { setPage(1); setEdition(e.target.value.replace(/[^0-9]/g,'')) }}/></label>}
        </div>
        {message && <p className="studio-notice" role="status">{message}</p>}
        {loading ? <p className="studio-state">Loading media catalogue…</p> : rows.length ? <div className="studio-item-grid">{rows.map(item => <article className="studio-item" key={item.id}>
          <div className={'studio-art' + (item.preview_url || item.player_url ? ' studio-art-available' : '')}>
            {item.preview_url ? <button className="studio-preview-trigger" type="button" onClick={() => setPreview({kind: 'image', url: backendUrl(item.preview_url), title: item.title})} aria-label={`Preview ${item.title}`}><img src={backendUrl(item.preview_url)} loading="lazy" alt="" onError={(event) => { event.currentTarget.hidden = true }} /><span>View image</span></button>
            : item.player_url && safePlayer(item.player_url) ? <button className="studio-preview-trigger studio-play-trigger" type="button" onClick={() => setPreview({kind: 'video', url: safePlayer(item.player_url), title: item.title})} aria-label={`Preview ${item.title}`}><span className="studio-play-icon" aria-hidden="true">▶</span><strong>Watch or preview stream</strong></button>
            : <span className="studio-art-placeholder" aria-hidden="true">{selected?.icon}</span>}
            <small>{library === 'hosted' ? 'YOUTUBE / LIVE' : selected?.name.toUpperCase()} · #{item.id}</small>
          </div>
          <div className="studio-item-body"><div className="studio-item-meta"><span className={'studio-status studio-status-' + item.state}>{item.state}</span>{item.edition && <span>Edition {item.edition}</span>}</div><h3>{item.title}</h3><div className="studio-item-actions">{user.owner || user.libraries?.includes(library) ? <button type="button" disabled={pending !== null} onClick={() => addToFoundation(item)}>Add to Foundation catalogue</button> : null}{canEdit && item.metadata && <button type="button" disabled={pending !== null} onClick={() => setEditing(editing === item.id ? null : item.id)}>{editing === item.id ? 'Cancel edit' : 'Edit details'}</button>}{canPublish && ['photos','videos','hosted','recordings','flyers','promotions','activities'].includes(library) && <button type="button" disabled={pending !== null} onClick={() => publish(item, item.state === 'published' ? 'withdraw' : 'publish')}>{pending === item.id ? 'Saving…' : item.state === 'published' ? 'Withdraw' : 'Publish'}</button>}{!canEdit && !canPublish && <span>Read-only catalogue</span>}</div>
          {editing === item.id && <form className="studio-edit-form" onSubmit={event => saveMetadata(event, item)}><strong>Editorial details</strong>{Object.entries(item.metadata || {}).map(([name,value]) => <label key={name}>{name.replaceAll('_',' ')}{typeof value === 'boolean' ? <input name={name} type="checkbox" defaultChecked={value} /> : <input name={name} type={typeof value === 'number' ? 'number' : 'text'} min={typeof value === 'number' ? 0 : undefined} maxLength={typeof value === 'number' ? undefined : 5000} defaultValue={value ?? ''} />}</label>)}<button type="submit" disabled={pending !== null}>Save changes</button></form>}</div>
        </article>)}</div> : <div className="studio-state"><strong>No media records match this view.</strong><p>Use the filters to find existing items. Try a different search or clear the filters. YouTube links can be added now; new file uploads require private storage activation.</p></div>}
        {more && <div className="studio-pagination"><button type="button" disabled={loading || page >= 100} onClick={() => setPage(current => current + 1)}>{loading ? 'Loading…' : 'Load more media'}</button></div>}
      </section>
      {user.owner || user.libraries?.length ? <StudioDestinations user={user} editions={uploadInfo.editions} library={library} sourceLinkRefresh={revision} focusAsset={focusAsset} /> : null}
      {preview && <div className="studio-preview-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setPreview(null) }}>
        <section className="studio-preview-dialog" role="dialog" aria-modal="true" aria-label={`Preview: ${preview.title}`}>
          <header><div><span className="studio-kicker">MEDIA PREVIEW</span><h2>{preview.title}</h2></div><button type="button" autoFocus onClick={() => setPreview(null)} aria-label="Close media preview">✕</button></header>
          {preview.kind === 'video' ? <><div className="studio-preview-video"><iframe title={preview.title} src={preview.url} allow="encrypted-media; picture-in-picture; fullscreen" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" /></div><p>Player availability depends on the video's YouTube or Vimeo visibility and embedding settings.</p><a href={preview.url} target="_blank" rel="noopener noreferrer">Open video externally ↗</a></> : <img src={preview.url} alt={preview.title} />}
        </section>
      </div>}
      <aside className="studio-storage-note"><strong>Publishing and private storage</strong><p>All library records and publishing actions are authorized by the backend. New uploads are unavailable until owner-approved R2 activation; when activated, all uploads save as drafts.</p></aside>
    </main>
  </div>
}
