import { resolveMediaUrl } from '../../services/mediaUrl'
import { useEffect, useRef, useState } from 'react'
import { Container } from '../layout/SiteChrome'
import './CampShowcase.css'

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
  const total = lecturers.length
  useEffect(() => { setActive(0) }, [lecturers])
  if (!total) return null
  const current = Math.min(active, total - 1)
  const move = (step) => setActive(index => (index + step + total) % total)
  // Only render visible neighbours, even when the library grows very large.
  const positions = total === 1 ? [0] : total === 2 ? [-1, 0] : total === 3 ? [-1, 0, 1] : [-2, -1, 0, 1, 2]
  const slides = positions.map(offset => ({
    offset, lecturer: lecturers[(current + offset + total) % total],
  }))
  return <div className="showcase-rail" role="region"
    aria-roledescription="carousel"
    aria-label={historical ? 'Lecturers from earlier camp editions' : 'Upcoming camp lecturers'}
    onKeyDown={event => {
      if (event.target.closest('a')) return
      if (event.key === 'ArrowLeft') { event.preventDefault(); move(-1) }
      if (event.key === 'ArrowRight') { event.preventDefault(); move(1) }
    }}
    onTouchStart={event => { touchStart.current = event.touches[0]?.clientX ?? null }}
    onTouchEnd={event => {
      if (touchStart.current === null) return
      const delta = (event.changedTouches[0]?.clientX ?? touchStart.current) - touchStart.current
      touchStart.current = null
      if (Math.abs(delta) > 45 && total > 1) move(delta < 0 ? 1 : -1)
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
      <span aria-live="polite" className="showcase-rail-count">{current + 1} / {total}</span>
      <button type="button" onClick={() => move(1)} aria-label="Next lecturer">›</button>
    </div>}
    <p className="showcase-rail-hint">Select the flyer to view it at full size.</p>
  </div>
}

export default function CampShowcase() {
  const [data, setData] = useState({ upcoming: [], previous: [], activities: [] })
  const [status, setStatus] = useState('loading')
  const activitiesSection = useRef(null)
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
  useEffect(() => {
    if (!activitiesSection.current || typeof IntersectionObserver === 'undefined') return undefined
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.add('showcase-entered'); observer.unobserve(entry.target) } })
    }, { threshold: .08 })
    activitiesSection.current.querySelectorAll('.showcase-activity').forEach(card => observer.observe(card))
    return () => observer.disconnect()
  }, [data.activities])
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
    {data.activities.length > 0 && <section className="showcase-activities" ref={activitiesSection} aria-labelledby="showcase-activities-title"><Container>
      <span className="eyebrow">LEARN · CONNECT · GROW</span><h2 id="showcase-activities-title">What to expect at camp</h2>
      <div className="showcase-activity-grid">{data.activities.map(item => <article className="showcase-activity" key={item.id}>
        {item.image_url && <img src={resolveMediaUrl(item.image_url)} alt={item.alt_text || item.title} loading="lazy" decoding="async" />}
        <div><small>{item.category}</small><h3>{item.title}</h3>{item.description && <p>{item.description}</p>}</div>
      </article>)}</div>
    </Container></section>}
  </div>
}
