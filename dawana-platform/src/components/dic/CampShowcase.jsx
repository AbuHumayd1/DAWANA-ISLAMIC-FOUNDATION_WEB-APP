import { resolveMediaUrl } from '../../services/mediaUrl'
import { useEffect, useRef, useState } from 'react'
import { Container } from '../layout/SiteChrome'
import './CampShowcase.css'
import MediaGlide from '../media/MediaGlide'

const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

/** Flyer-first, bounded carousel. No edition selector, status badges, or directory cards. */
export function LecturerCard({ lecturer }) {
  return <a className="showcase-flyer" href={resolveMediaUrl(lecturer.image_url)}
    target="_blank" rel="noopener noreferrer"
    aria-label={`Open full lecturer flyer for ${lecturer.name || 'camp lecturer'}`}>
    <img src={resolveMediaUrl(lecturer.image_url)}
      alt={lecturer.alt_text || lecturer.name || 'Camp lecturer flyer'}
      loading="lazy" decoding="async" />
  </a>
}

export function LecturerRail({ lecturers, historical = false }) {
  const [active, setActive] = useState(0)
  const touchStart = useRef(null)
  const railRef = useRef(null)
  const [paused,setPaused] = useState(false)
  const [inView,setInView] = useState(false)
  const [interacting,setInteracting] = useState(false)
  const total = lecturers.length
  useEffect(() => { setActive(0) }, [lecturers])
  useEffect(() => {
    if(!railRef.current || typeof IntersectionObserver==='undefined') return
    const observer = new IntersectionObserver(entries => setInView(entries[0].isIntersecting), {threshold:.3})
    observer.observe(railRef.current)
    return () => observer.disconnect()
  }, [total])
  useEffect(() => {
    if(total<2 || paused || interacting || !inView) return
    const media=window.matchMedia('(prefers-reduced-motion: reduce)')
    const timer=window.setInterval(()=>{if(!media.matches && !document.hidden)setActive(index=>(index+1)%total)},5500)
    return ()=>window.clearInterval(timer)
  },[total,paused,interacting,inView])
  if (!total) return null
  const current = Math.min(active, total - 1)
  const move = (step) => setActive(index => (index + step + total) % total)
  // Only render visible neighbours, even when the library grows very large.
  const positions = total === 1 ? [0] : total === 2 ? [-1, 0] : total === 3 ? [-1, 0, 1] : [-2, -1, 0, 1, 2]
  const slides = positions.map(offset => ({
    offset, lecturer: lecturers[(current + offset + total) % total],
  }))
  return <div ref={railRef} className="showcase-rail" role="region" onPointerEnter={e=>{if(e.pointerType==='mouse')setInteracting(true)}} onPointerLeave={e=>{if(e.pointerType==='mouse')setInteracting(false)}} onFocusCapture={()=>setInteracting(true)} onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget))setInteracting(false)}}
    aria-roledescription="carousel"
    aria-label={historical ? 'Lecturers from earlier camp editions' : 'Upcoming camp lecturers'}
    onKeyDown={event => {
      if (event.target.closest('a')) return
      if (event.key === 'ArrowLeft') { event.preventDefault(); move(-1) }
      if (event.key === 'ArrowRight') { event.preventDefault(); move(1) }
    }}
    onTouchStart={event => { if(event.target.closest('button')) return; touchStart.current = [event.touches[0].clientX,event.touches[0].clientY] }}
    onTouchCancel={()=>{touchStart.current=null}}
    onTouchEnd={event => {
      if (touchStart.current === null) return
      const [x,y] = touchStart.current
      const delta = event.changedTouches[0].clientX-x
      const vertical = event.changedTouches[0].clientY-y
      touchStart.current = null
      if (Math.abs(delta) > 45 && Math.abs(delta)>Math.abs(vertical) && total > 1) {setPaused(true);move(delta < 0 ? 1 : -1)}
    }}>
    <div className="showcase-rail-track">
      {slides.map(({ offset, lecturer }) => <div
        key={offset} className={`showcase-rail-item${offset === 0 ? ' is-active' : ''}`}
        data-offset={offset}>
        {offset === 0 ? <LecturerCard lecturer={lecturer} /> :
          <button className="showcase-rail-preview" type="button" tabIndex={-1}
            aria-label={`Show ${lecturer.name || 'lecturer'}`}
            onClick={() => move(offset)}>
            <img src={resolveMediaUrl(lecturer.image_url)} alt="" loading="lazy" decoding="async" />
          </button>}
      </div>)}
    </div>
    {total > 1 && <div className="showcase-rail-controls">
      <button type="button" onClick={() => move(-1)} aria-label="Previous lecturer">‹</button>
      <button className="showcase-motion" type="button" onClick={()=>setPaused(v=>!v)} aria-label={paused?"Resume lecturer carousel":"Pause lecturer carousel"}>{paused?"Resume slides":"Pause slides"}</button>
      <span aria-live={paused?"polite":"off"} className="showcase-rail-count">{current + 1} / {total}</span>
      <button type="button" onClick={() => move(1)} aria-label="Next lecturer">›</button>
    </div>}
    <p className="showcase-rail-hint">Select the flyer to view it at full size.</p>
  </div>
}

export default function CampShowcase() {
  const [data, setData] = useState({ upcoming: [], previous: [], activities: [] })
  const [status, setStatus] = useState('loading')
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${base}/dic/showcase/`, { credentials: 'omit', cache: 'no-store', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Showcase unavailable')
        const result = await response.json()
        if (![result.upcoming, result.previous, result.activities].every(Array.isArray)) throw new Error('Invalid showcase')
        if (controller.signal.aborted) return
        setData(result)
        setStatus('ready')
      }).catch(error => { if (error.name !== 'AbortError') setStatus('error') })
    return () => controller.abort()
  }, [])
  // Empty modules should not occupy full-screen placeholders in the public landing page.
  if (status !== 'ready') return null
  return <div className="dic-showcase">
    {data.upcoming.length > 0 && <section className="showcase-upcoming" aria-labelledby="showcase-upcoming-title"><Container>
      <span className="eyebrow">DIC LECTURERS</span>
      <h2 id="showcase-upcoming-title">Meet the camp lecturers</h2>
      <LecturerRail lecturers={data.upcoming} />
    </Container></section>}
    {data.previous.length > 0 && <section className="showcase-previous" aria-labelledby="showcase-previous-title"><Container>
      <span className="eyebrow">FROM THE CAMP ARCHIVE</span>
      <h2 id="showcase-previous-title">Lecturers from previous editions</h2>
      <LecturerRail lecturers={data.previous} historical />
    </Container></section>}
    {data.activities.length > 0 && <section className="showcase-activities" aria-labelledby="showcase-activities-title"><Container>
      <span className="eyebrow">LEARN · CONNECT · GROW</span><h2 id="showcase-activities-title">What to expect at camp</h2>
      <MediaGlide count={data.activities.length} label="Camp activities" className="showcase-activity-grid">{data.activities.map(item => <article className="showcase-activity" key={item.id}>
        {item.image_url && <a className="showcase-activity-image" href={resolveMediaUrl(item.image_url)} target="_blank" rel="noopener noreferrer"><img src={resolveMediaUrl(item.image_url)} alt={item.alt_text || item.title} loading="lazy" decoding="async" /></a>}
        <div><small>{item.category}</small><h3>{item.title}</h3>{item.description && <details className="showcase-activity-description"><summary>About this activity</summary><p>{item.description}</p></details>}</div>
      </article>)}</MediaGlide>
    </Container></section>}
  </div>
}
