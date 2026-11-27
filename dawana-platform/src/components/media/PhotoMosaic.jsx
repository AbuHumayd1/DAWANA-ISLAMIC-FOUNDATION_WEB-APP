import { useEffect, useId, useRef, useState } from 'react'
import { Container } from '../layout/SiteChrome'
import { backendUrl } from '../../services/productionContract'
import './PhotoMosaic.css'

const api = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
const COPY = {
  foundation_home: {
    eyebrow: 'OUR IMPACT IN PICTURES',
    title: 'Faith. Knowledge. Community.',
    description: 'Moments of learning, service and brotherhood.',
    label: 'Foundation photographs',
  },
  dic_memories: {
    eyebrow: 'THROUGH THE YEARS',
    title: 'Moments worth remembering.',
    description: 'The Darul Islam Camp experience in pictures.',
    label: 'Camp photographs',
  },
}

export default function PhotoMosaic({ destination }) {
  const [photos, setPhotos] = useState([])
  const [selected, setSelected] = useState(null)
  const headingId = useId()
  const dialog = useRef(null)
  const trigger = useRef(null)
  const open = selected !== null && !!photos[selected]
  const copy = COPY[destination]

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${api}/dic/studio/public-placements/?destination=${encodeURIComponent(destination)}&view=photos`, {
      credentials: 'omit', cache: 'no-store', signal: controller.signal,
    }).then(response => {
      if (!response.ok) throw new Error('Photographs unavailable')
      return response.json()
    }).then(data => {
      if (!Array.isArray(data.items)) throw new Error('Invalid photograph feed')
      if (controller.signal.aborted) return
      const unique = new Map()
      for (const row of data.items) {
        if (row.source_kind !== 'photos' || typeof row.url !== 'string' ||
            !row.url.startsWith('/api/v1/dic/') || row.url.length > 400) continue
        if (!unique.has(row.url)) unique.set(row.url, row)
        if (unique.size === 9) break
      }
      setPhotos([...unique.values()])
    }).catch(error => {
      if (error.name !== 'AbortError') setPhotos([])
    })
    return () => controller.abort()
  }, [destination])

  useEffect(() => {
    if (!open || !dialog.current) return
    const node = dialog.current
    node.showModal()
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      node.close()
      document.body.style.overflow = previous
      trigger.current?.focus()
    }
  }, [open])

  function move(delta) {
    setSelected(index => (index + delta + photos.length) % photos.length)
  }

  if (!copy || !photos.length) return null
  return <section className="photo-mosaic" aria-labelledby={headingId}>
    <Container>
      <header className="photo-mosaic-heading">
        <span className="eyebrow">{copy.eyebrow}</span>
        <h2 id={headingId}>{copy.title}</h2>
        <p>{copy.description}</p>
      </header>
      <div className="photo-mosaic-grid">
        {photos.map((photo,index) => <button type="button" key={photo.url}
          className="photo-mosaic-tile" aria-label={`View photograph ${index+1}: ${photo.alt_text || photo.title || copy.label}`}
          onClick={event => { trigger.current = event.currentTarget; setSelected(index) }}>
          <img src={backendUrl(photo.url)} alt={photo.alt_text || photo.title || copy.label} loading="lazy" decoding="async"/>
        </button>)}
      </div>
    </Container>
    <dialog ref={dialog} className="photo-mosaic-viewer" aria-label={copy.label}
      onCancel={event => { event.preventDefault(); setSelected(null) }}
      onClick={event => { if (event.target === event.currentTarget) setSelected(null) }}
      onKeyDown={event => {
        if (event.key === 'ArrowLeft' && photos.length > 1) { event.preventDefault(); move(-1) }
        if (event.key === 'ArrowRight' && photos.length > 1) { event.preventDefault(); move(1) }
      }}>
      {open && <div className="photo-mosaic-viewer-inner">
        <div className="photo-mosaic-viewer-tools"><span aria-live="polite">{selected+1} / {photos.length}</span><button type="button" autoFocus onClick={()=>setSelected(null)} aria-label="Close photograph viewer">Close ×</button></div>
        <img src={backendUrl(photos[selected].url)} alt={photos[selected].alt_text || photos[selected].title || copy.label}/>
        {photos.length > 1 && <div className="photo-mosaic-viewer-nav">
          <button type="button" onClick={()=>move(-1)} aria-label="Previous photograph">‹</button>
          <button type="button" onClick={()=>move(1)} aria-label="Next photograph">›</button>
        </div>}
      </div>}
    </dialog>
  </section>
}
