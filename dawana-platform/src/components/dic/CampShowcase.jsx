import { useEffect, useRef, useState } from 'react'
import { Container } from '../layout/SiteChrome'
import './CampShowcase.css'

const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export function LecturerCard({ lecturer, historical = false }) {
  const verified = lecturer.confirmed === true
  return <article className={`showcase-lecturer${lecturer.featured ? ' showcase-featured' : ''}`}>
    <div className="showcase-portrait"><img src={lecturer.image_url} alt={lecturer.alt_text} loading="lazy" decoding="async" width="640" height="720" />{lecturer.featured && <span>Featured lecturer</span>}</div>
    <div className="showcase-profile"><small>{lecturer.edition.name}</small><h3>{lecturer.name}</h3>{lecturer.designation && <p className="showcase-designation">{lecturer.designation}</p>}
      {!historical && <span className={`showcase-status${verified ? ' is-verified' : ''}`}>{verified ? 'Participation confirmed' : 'Participation awaiting confirmation'}</span>}
      {historical && !verified && <span className="showcase-status">Historical profile · topic awaiting verification</span>}
      {lecturer.topic && (!historical || verified) && <p className="showcase-topic"><strong>{historical ? 'Verified lecture topic' : 'Approved topic'}</strong>{lecturer.topic}</p>}
      <p className="showcase-biography">{lecturer.biography}</p>
    </div>
  </article>
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
    <section className="showcase-upcoming" aria-labelledby="showcase-upcoming-title"><Container><span className="eyebrow">KNOWLEDGE & REFLECTION</span><h2 id="showcase-upcoming-title">Upcoming DIC 2026 Lecturers</h2><p className="showcase-intro">Approved profiles and topics, with participation status clearly stated.</p>
      {feedback && <p role="status">{feedback}</p>}
      {status === 'ready' && !data.upcoming.length && <div className="showcase-empty"><h3>Meet the lecturers when details are approved</h3><p>Lecturer announcements will appear here after editorial approval. No participation is assumed.</p></div>}
      <div className="showcase-lecturer-grid">{data.upcoming.map(item => <LecturerCard key={item.id} lecturer={item} />)}</div>
    </Container></section>
    <section className="showcase-previous" aria-labelledby="showcase-previous-title"><Container><span className="eyebrow">FROM THE CAMP ARCHIVE</span><h2 id="showcase-previous-title">Lecturers From Previous Editions</h2>
      {feedback && <p role="status">{feedback}</p>}
      {!!data.previous.length && <label className="showcase-filter">Past camp edition<select aria-label="Past lecturer edition" value={edition} onChange={event => setEdition(event.target.value)}><option value="">All past editions</option>{editions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select><span role="status">{previous.length} {previous.length === 1 ? 'profile' : 'profiles'}</span></label>}
      {status === 'ready' && !previous.length && <div className="showcase-empty"><p>No approved historical lecturer profiles are available{edition ? ' for this edition' : ' yet'}.</p></div>}
      <div className="showcase-lecturer-grid">{previous.map(item => <LecturerCard key={item.id} lecturer={item} historical />)}</div>
    </Container></section>
    <section className="showcase-activities" ref={activitiesSection} aria-labelledby="showcase-activities-title"><Container><span className="eyebrow">LEARN · CONNECT · GROW</span><h2 id="showcase-activities-title">What to Expect at DIC 2026</h2><p className="showcase-intro">Explore the activities approved for this edition. Programme details are shared only when authorized.</p>
      {feedback && <p role="status">{feedback}</p>}
      {status === 'ready' && !data.activities.length && <div className="showcase-empty"><h3>The programme is being prepared</h3><p>Committee-approved activities will appear here when ready. No schedule has been announced in this section.</p></div>}
      <div className="showcase-activity-grid">{data.activities.map(item => <article className={`showcase-activity${item.featured ? ' showcase-featured' : ''}`} key={item.id}>
        {item.image_url && <img src={item.image_url} alt={item.alt_text} loading="lazy" decoding="async" width="800" height="600" />}
        <div><small>{item.category}{item.featured ? ' · Featured activity' : ''}</small><h3>{item.title}</h3><p>{item.description}</p></div>
      </article>)}</div>
    </Container></section>
  </div>
}
