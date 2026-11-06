import { resolveMediaUrl } from '../../services/mediaUrl'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Container } from '../layout/SiteChrome'
import './DICLandingRefinements.css'
const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')
const localPreview = import.meta.env.DEV && typeof window !== 'undefined' && ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)

function PromoCard({ item }) {
  const [play, setPlay] = useState(false)
  return <article className="dic-promo-card">
    <div className="dic-promo-screen">{play ? <video controls autoPlay playsInline preload="metadata" poster={resolveMediaUrl(item.poster_url)} aria-label={item.title}><source src={resolveMediaUrl(item.video_url)} type="video/mp4" />Your browser cannot play this video.</video> : <button type="button" onClick={() => setPlay(true)} aria-label={`Play ${item.title}`}><img src={resolveMediaUrl(item.poster_url)} alt={item.alt_text} loading="lazy" decoding="async" width="960" height="540" /><span className="dic-play-symbol" aria-hidden="true">▶</span></button>}</div>
    <div className="dic-promo-copy"><h3>{item.title}</h3>{item.description && <p>{item.description}</p>}</div>
  </article>
}

function Flyer({ flyer, onRegister, canRegister }) {
  const [open, setOpen] = useState(false)
  const dialog = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const node = dialog.current
    const opener = document.activeElement
    node.showModal()
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { node.close(); document.body.style.overflow = overflow; opener?.focus() }
  }, [open])
  return <section className="dic-official-flyer" aria-labelledby="dic-flyer-title"><Container><div className="dic-flyer-layout">
    <button className="dic-flyer-open" type="button" onClick={() => setOpen(true)} aria-label={`Enlarge ${flyer.title}`}><img src={resolveMediaUrl(flyer.image_url)} alt={flyer.alt_text} loading="lazy" decoding="async" width="800" height="1100" /><span>View the official flyer ↗</span></button>
    <div><span className="eyebrow">THE OFFICIAL INVITATION</span><h2 id="dic-flyer-title">{flyer.title}</h2><p>Take a closer look at the official camp flyer, then explore registration for your next DIC experience.</p><button className="button" type="button" onClick={onRegister} disabled={!canRegister}>Register for DIC ↗</button></div>
  </div></Container><dialog className="dic-flyer-viewer" ref={dialog} aria-label={flyer.title} onCancel={() => setOpen(false)} onClick={event => { if (event.target === event.currentTarget) setOpen(false) }}><button type="button" autoFocus onClick={() => setOpen(false)} aria-label="Close official flyer">Close ×</button>{open && <img src={resolveMediaUrl(flyer.image_url)} alt={flyer.alt_text} />}</dialog></section>
}

export default function DICEditorial({ onRegister, canRegister }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${base}/dic/editorial/`, { credentials: 'omit', cache: 'no-store', signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error('Unavailable'); return response.json() })
      .then(result => { if (Array.isArray(result.experiences) && Array.isArray(result.introductions)) setData(result) })
      .catch(() => {})
    return () => controller.abort()
  }, [])
  if (!data && !localPreview) return null
  const content = data || { flyer: null, experiences: [], introductions: [] }
  return <>
    {content.flyer ? <Flyer flyer={content.flyer} onRegister={onRegister} canRegister={canRegister} /> : localPreview && <section className="dic-official-flyer"><Container><div className="dic-flyer-layout"><div className="dic-preview-placeholder dic-preview-flyer"><span aria-hidden="true">✧</span><strong>Flyer coming soon</strong><small>Local preview · awaiting editorial approval</small></div><div><span className="eyebrow">THE OFFICIAL INVITATION</span><h2>Official DIC flyer</h2><p>The approved flyer will appear here, with an option to enlarge it.</p><button className="button" type="button" onClick={onRegister} disabled={!canRegister}>Register for DIC ↗</button></div></div></Container></section>}
    {[[content.experiences.slice(0, 3), 'THROUGH THEIR EYES', "Previous campers’ experiences", 'Approved MP4 stories from participants at previous editions.', 3], [content.introductions.slice(0, 2), 'LOOKING AHEAD', 'Upcoming camp promotional videos', 'Discover what to expect at the upcoming camp through approved introductory MP4 videos.', 2]].map(([items, eyebrow, title, description, limit]) => (items.length > 0 || localPreview) && <section className="dic-promo-section" key={eyebrow}><Container><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{description}</p><div className="dic-promo-grid">{items.length ? items.map(item => <PromoCard key={item.id} item={item} />) : Array.from({ length: limit }, (_, index) => <div className="dic-preview-placeholder" key={index}><span aria-hidden="true">▷</span><strong>Awaiting approved video</strong><small>Local preview · {eyebrow === 'LOOKING AHEAD' ? 'Camp introduction' : 'Camper experience'}</small></div>)}</div></Container></section>)}
    {(content.experiences.length > 0 || content.introductions.length > 0 || localPreview) && <Container><p className="dic-lecture-link">Looking for lectures and foundation recordings? <Link to="/media">Visit our Media page ↗</Link></p></Container>}
  </>
}
