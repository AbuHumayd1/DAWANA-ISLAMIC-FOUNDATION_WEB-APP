import { useEffect, useRef, useState } from 'react'
import { Container } from '../layout/SiteChrome'
import './MemoriesGallery.css'

const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export default function MemoriesGallery() {
  const [photos, setPhotos] = useState([])
  const [state, setState] = useState('loading')
  const [edition, setEdition] = useState('')
  const [activity, setActivity] = useState('')
  const [selected, setSelected] = useState(null)
  const dialog = useRef(null)
  const returnFocus = useRef(null)
  const section = useRef(null)
  const viewerOpen = selected !== null

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${base}/dic/memories/`, { signal: controller.signal, credentials: 'omit', cache: 'no-store' })
      .then(async response => {
        if (!response.ok) throw new Error('Gallery unavailable')
        const data = await response.json()
        if (!Array.isArray(data.photographs)) throw new Error('Invalid gallery')
        setPhotos(data.photographs)
        setState('ready')
      }).catch(error => { if (error.name !== 'AbortError') setState('error') })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!section.current || typeof IntersectionObserver === 'undefined') return undefined
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        entry.target.classList.add('memories-visible')
        observer.unobserve(entry.target)
      }
    }, { threshold: 0.08 })
    section.current.querySelectorAll('.memory-card').forEach(card => observer.observe(card))
    return () => observer.disconnect()
  }, [photos, edition, activity])

  useEffect(() => {
    if (!viewerOpen) return undefined
    const node = dialog.current
    node.showModal()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      node.close()
      document.body.style.overflow = previousOverflow
      returnFocus.current?.focus()
    }
  }, [viewerOpen]) // Keep the dialog open while changing photographs.

  const editions = [...new Map(photos.map(photo => [String(photo.edition.id), photo.edition.name])).entries()]
  const activities = [...new Map(photos.flatMap(photo => photo.activities.map(tag => [String(tag.id), tag.name]))).entries()]
  const visible = photos.filter(photo => (!edition || String(photo.edition.id) === edition) && (!activity || photo.activities.some(tag => String(tag.id) === activity)))
  const current = visible.find(photo => photo.id === selected)
  const move = direction => {
    const index = visible.findIndex(photo => photo.id === selected)
    setSelected(visible[(index + direction + visible.length) % visible.length].id)
  }

  return <section className="dic-memories" ref={section} aria-labelledby="memories-title"><Container>
    <div className="memories-heading"><div><span className="eyebrow">THE CAMP SCRAPBOOK</span><h2 id="memories-title">Moments worth keeping</h2><p>A window into past camp experiences, shared through approved photographs.</p></div><span className="memories-stamp" aria-hidden="true">Learning.<br />Belonging.<br />Memories.</span></div>
    {state === 'loading' && <p role="status">Opening the camp scrapbook…</p>}
    {state === 'error' && <p role="status">The scrapbook is temporarily unavailable. Please visit again later.</p>}
    {state === 'ready' && photos.length === 0 && <div className="memories-empty"><span aria-hidden="true">✧</span><h3>Our scrapbook is being prepared</h3><p>Approved photographs from past camps will appear here when they are available.</p></div>}
    {photos.length > 0 && <>
      <div className="memories-filters"><label>Camp edition<select aria-label="Camp edition" value={edition} onChange={event => setEdition(event.target.value)}><option value="">All editions</option>{editions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label><label>Activity<select aria-label="Activity" value={activity} onChange={event => setActivity(event.target.value)}><option value="">All activities</option>{activities.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label><p role="status">{visible.length} {visible.length === 1 ? 'photograph' : 'photographs'}</p></div>
      <div className="memories-board">{visible.map((photo, index) => <article className="memory-card" key={photo.id} style={{ '--tilt': `${index % 2 ? 2 : -2}deg`, '--delay': `${index % 4 * 70}ms` }}><button type="button" className="memory-open" aria-label={`View photograph: ${photo.caption}`} onClick={event => { returnFocus.current = event.currentTarget; setSelected(photo.id) }}><span className="memory-pin" aria-hidden="true" /><img src={photo.image_url} alt={photo.alt_text} loading="lazy" decoding="async" width="800" height="600" /><span className="memory-caption"><small>{photo.edition.name}</small><strong>{photo.caption}</strong></span></button></article>)}</div>
      {!visible.length && <p>No approved photographs match these filters.</p>}
    </>}
    <dialog ref={dialog} className="memory-viewer" aria-label="Camp photograph viewer" onCancel={() => setSelected(null)} onClick={event => { if (event.target === event.currentTarget) setSelected(null) }} onKeyDown={event => { if (event.key === 'Tab') { const buttons = [...event.currentTarget.querySelectorAll('button:not([disabled])')]; const first = buttons[0]; const last = buttons[buttons.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() } } if (event.key === 'ArrowRight' && current) { event.preventDefault(); move(1) } if (event.key === 'ArrowLeft' && current) { event.preventDefault(); move(-1) } }}>
      <button type="button" className="memory-close" autoFocus onClick={() => setSelected(null)} aria-label="Close photograph viewer">Close ×</button>
      {current && <div className="memory-viewer-content"><img src={current.image_url} alt={current.alt_text} /><p aria-live="polite"><strong>{current.caption}</strong><span>{current.edition.name}</span></p><div className="memory-viewer-nav"><button type="button" onClick={() => move(-1)} disabled={visible.length < 2}>← Previous photograph</button><button type="button" onClick={() => move(1)} disabled={visible.length < 2}>Next photograph →</button></div></div>}
    </dialog>
  </Container></section>
}
