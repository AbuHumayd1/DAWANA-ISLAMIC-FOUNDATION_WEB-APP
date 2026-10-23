import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Container } from '../layout/SiteChrome'
import './DICLandingRefinements.css'
const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

function PromoCard({ item }) {
  const [play, setPlay] = useState(false)
  return <article className="dic-promo-card">
    <div className="dic-promo-screen">{play ? <video controls autoPlay playsInline preload="metadata" poster={item.poster_url} aria-label={item.title}><source src={item.video_url} type="video/mp4" />Your browser cannot play this video.</video> : <button type="button" onClick={() => setPlay(true)} aria-label={`Play ${item.title}`}><img src={item.poster_url} alt={item.alt_text} loading="lazy" decoding="async" width="960" height="540" /><span className="dic-play-symbol" aria-hidden="true">▶</span></button>}</div>
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
    <button className="dic-flyer-open" type="button" onClick={() => setOpen(true)} aria-label={`Enlarge ${flyer.title}`}><img src={flyer.image_url} alt={flyer.alt_text} loading="lazy" decoding="async" width="800" height="1100" /><span>View the official flyer ↗</span></button>
    <div><span className="eyebrow">THE OFFICIAL INVITATION</span><h2 id="dic-flyer-title">{flyer.title}</h2><p>Take a closer look at the official camp flyer, then explore registration for your next DIC experience.</p><button className="button" type="button" onClick={onRegister} disabled={!canRegister}>Register for DIC ↗</button></div>
  </div></Container><dialog className="dic-flyer-viewer" ref={dialog} aria-label={flyer.title} onCancel={() => setOpen(false)} onClick={event => { if (event.target === event.currentTarget) setOpen(false) }}><button type="button" autoFocus onClick={() => setOpen(false)} aria-label="Close official flyer">Close ×</button>{open && <img src={flyer.image_url} alt={flyer.alt_text} />}</dialog></section>
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
  if (!data) return null
  return <>
    {data.flyer && <Flyer flyer={data.flyer} onRegister={onRegister} canRegister={canRegister} />}
    {[[data.experiences.slice(0, 3), 'THROUGH THEIR EYES', 'Memories from previous editions'], [data.introductions.slice(0, 2), 'LOOKING AHEAD', 'A glimpse of the upcoming camp']].map(([items, eyebrow, title]) => items.length > 0 && <section className="dic-promo-section" key={eyebrow}><Container><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><div className="dic-promo-grid">{items.map(item => <PromoCard key={item.id} item={item} />)}</div></Container></section>)}
    {(data.experiences.length > 0 || data.introductions.length > 0) && <Container><p className="dic-lecture-link">Looking for lectures and foundation recordings? <Link to="/media">Visit our Media page ↗</Link></p></Container>}
  </>
}
