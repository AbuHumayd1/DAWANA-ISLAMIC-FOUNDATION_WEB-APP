import { resolveMediaUrl } from '../../services/mediaUrl'
import { useEffect, useRef, useState } from 'react'
import { Container } from '../layout/SiteChrome'
import './CampShowcase.css'

const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')
const localPreview = import.meta.env.DEV && typeof window !== 'undefined' && ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)

export function LecturerCard({ lecturer, historical = false }) {
  const verified = lecturer.confirmed === true
  return <article className={`showcase-lecturer${lecturer.featured ? ' showcase-featured' : ''}`}>
    <div className="showcase-portrait"><img src={resolveMediaUrl(lecturer.image_url)} alt={lecturer.alt_text} loading="lazy" decoding="async" width="640" height="720" />{lecturer.featured && <span>Featured lecturer</span>}</div>
    <div className="showcase-profile"><small>{lecturer.edition.name}</small><h3>{lecturer.name}</h3>{lecturer.designation && <p className="showcase-designation">{lecturer.designation}</p>}
      {!historical && <span className={`showcase-status${verified ? ' is-verified' : ''}`}>{verified ? 'Participation confirmed' : 'Participation awaiting confirmation'}</span>}
      {historical && !verified && <span className="showcase-status">Historical profile · topic awaiting verification</span>}
      {lecturer.topic && (!historical || verified) && <p className="showcase-topic"><strong>{historical ? 'Verified lecture topic' : 'Approved topic'}</strong>{lecturer.topic}</p>}
      <p className="showcase-biography">{lecturer.biography}</p>
    </div>
  </article>
}


/** An accessible, expanding editorial speaker rail; the source approval rules are unchanged. */
function LecturerRail({ lecturers, historical = false }) {
  const [active, setActive] = useState(0)
  useEffect(() => { setActive(0) }, [lecturers])
  if (!lecturers.length) return null
  const selected = Math.min(active, lecturers.length - 1)
  const move = offset => setActive(index => (index + offset + lecturers.length) % lecturers.length)
  return <div className="showcase-rail" aria-label={historical ? 'Previous camp lecturers' : 'Upcoming camp lecturers'}>
    <div className="showcase-rail-track">
      {lecturers.map((lecturer, index) =>
        <div key={lecturer.id} className={`showcase-rail-item${index === selected ? ' is-active' : ''}`}
          data-distance={Math.min(Math.abs(index-selected), lecturers.length-Math.abs(index-selected))}>
          {index === selected ? <LecturerCard lecturer={lecturer} historical={historical} /> :
            <button className="showcase-rail-preview" type="button"
              onClick={() => setActive(index)} aria-label={`View lecturer ${lecturer.name}`}>
              <img src={resolveMediaUrl(lecturer.image_url)} alt="" loading="lazy" decoding="async" />
              <span>{lecturer.name}</span>
            </button>}
        </div>)}
    </div>
    {lecturers.length > 1 && <div className="showcase-rail-controls">
      <button type="button" onClick={() => move(-1)} aria-label="Previous lecturer">← Previous</button>
      <span role="status" aria-live="polite">{selected + 1} / {lecturers.length}</span>
      <button type="button" onClick={() => move(1)} aria-label="Next lecturer">Next →</button>
    </div>}
  </div>
}

export default function CampShowcase() {
  const [data, setData] = useState({ upcoming: [], previous: [], activities: [] })
  const [status, setStatus] = useState('loading')
  const [edition, setEdition] = useState('')
  const activitiesSection = useRef(null)
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${base}/dic/showcase/`, { credentials: 'omit', cache: 'no-store', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Showcase unavailable')
        const result = await response.json()
        if (![result.upcoming, result.previous, result.activities].every(Array.isArray)) throw new Error('Invalid showcase')
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
  const editions = [...new Map(data.previous.map(item => [String(item.edition.id), item.edition.name])).entries()]
  const previous = data.previous.filter(item => !edition || String(item.edition.id) === edition)
  const feedback = status === 'loading' ? 'Loading approved camp content…' : status === 'error' ? 'Camp content is temporarily unavailable. Please visit again later.' : null
  return <div className="dic-showcase">
    <section className="showcase-upcoming" aria-labelledby="showcase-upcoming-title"><Container><span className="eyebrow">KNOWLEDGE & REFLECTION</span><h2 id="showcase-upcoming-title">Meet the upcoming camp lecturers</h2><p className="showcase-intro">Approved profiles and topics, with participation status clearly stated.</p>
      {feedback && <p role="status">{feedback}</p>}
      {(status === 'ready' || localPreview) && !data.upcoming.length && <div className="showcase-empty"><h3>Meet the lecturers when details are approved</h3><p>Lecturer announcements will appear here after editorial approval. No participation is assumed.</p>{localPreview && <small>Local preview · awaiting approved lecturer profiles and topics</small>}</div>}
      <LecturerRail lecturers={data.upcoming} />
    </Container></section>
    <section className="showcase-previous" aria-labelledby="showcase-previous-title"><Container><span className="eyebrow">FROM THE CAMP ARCHIVE</span><h2 id="showcase-previous-title">Lecturers From Previous Editions</h2>
      {feedback && <p role="status">{feedback}</p>}
      {!!data.previous.length && <label className="showcase-filter">Past camp edition<select aria-label="Past lecturer edition" value={edition} onChange={event => setEdition(event.target.value)}><option value="">All past editions</option>{editions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select><span role="status">{previous.length} {previous.length === 1 ? 'profile' : 'profiles'}</span></label>}
      {(status === 'ready' || localPreview) && !previous.length && <div className="showcase-empty"><p>No approved historical lecturer profiles are available{edition ? ' for this edition' : ' yet'}.</p>{localPreview && <small>Local preview · previous lecturers</small>}</div>}
      <LecturerRail lecturers={previous} historical />
    </Container></section>
    <section className="showcase-activities" ref={activitiesSection} aria-labelledby="showcase-activities-title"><Container><span className="eyebrow">LEARN · CONNECT · GROW</span><h2 id="showcase-activities-title">What to expect at camp</h2><p className="showcase-intro">Explore the activities approved for this edition. Programme details are shared only when authorized.</p>
      {feedback && <p role="status">{feedback}</p>}
      {(status === 'ready' || localPreview) && !data.activities.length && <div className="showcase-empty"><h3>The programme is being prepared</h3><p>Committee-approved activities will appear here when ready. No schedule has been announced in this section.</p>{localPreview && <small>Local preview · awaiting approved activities; photographs are optional</small>}</div>}
      <div className="showcase-activity-grid">{data.activities.map(item => <article className={`showcase-activity${item.featured ? ' showcase-featured' : ''}`} key={item.id}>
        {item.image_url && <img src={resolveMediaUrl(item.image_url)} alt={item.alt_text} loading="lazy" decoding="async" width="800" height="600" />}
        <div><span className="dic-activity-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 3 15 9 21 12 15 15 12 21 9 15 3 12 9 9Z" /><circle cx="12" cy="12" r="2" /></svg></span><small>{item.category}{item.featured ? ' · Featured activity' : ''}</small><h3>{item.title}</h3><p>{item.description}</p></div>
      </article>)}</div>
    </Container></section>
  </div>
}
