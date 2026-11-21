import { useEffect, useRef, useState } from 'react'
import { Container } from '../layout/SiteChrome'
import { backendUrl } from '../../services/productionContract'
import './PublishedCarousels.css'

const api = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

function safeEmbed(url) {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' && ['player.vimeo.com', 'www.youtube-nocookie.com'].includes(parsed.hostname)
      && !parsed.port && !parsed.username && !parsed.password && !parsed.hash ? parsed.href : ''
  } catch { return '' }
}

function Story({ story }) {
  const [active, setActive] = useState(0)
  const [soundEnabled, setSoundEnabled] = useState(false)
  const [playingVideo, setPlayingVideo] = useState(false)
  const audio = useRef(null)
  const slides = story.slides || []
  const current = slides[active]
  const video = current && ['promotions', 'hosted', 'videos'].includes(current.kind)
  const soundtrackVideo = video && current.kind === 'promotions' && story.soundtrack_on_videos
  useEffect(() => {
    setPlayingVideo(false)
    if (audio.current) {
      if (video && !soundtrackVideo) audio.current.pause()
      else if (soundEnabled) audio.current.play().catch(() => setSoundEnabled(false))
    }
  }, [active, video, soundEnabled, soundtrackVideo])
  useEffect(() => () => { if (audio.current) audio.current.pause() }, [])
  function step(delta) { setActive(index => (index + delta + slides.length) % slides.length) }
  if (!current) return null
  return <article className="studio-story" aria-label={story.title}>
    <header className="studio-story-head">
      <span className="studio-story-kicker">{story.format === 'mixed' ? 'Mixed media story' : story.format === 'videos' ? 'Video story' : 'Photo story'}</span>
      <span className="studio-story-count" aria-live="polite">{active + 1} / {slides.length}</span>
    </header>
    <div className="studio-story-stage" onKeyDown={event => {
      if (event.key === 'ArrowLeft') { event.preventDefault(); step(-1) }
      if (event.key === 'ArrowRight') { event.preventDefault(); step(1) }
    }} tabIndex={0} aria-label={`Carousel: ${story.title}, use left and right arrows`}>
      <div className="studio-story-neighbour studio-story-neighbour--previous" aria-hidden="true">
        {['photos','flyers','activities','appearances'].includes(slides[(active - 1 + slides.length) % slides.length]?.kind) &&
          <img src={backendUrl(slides[(active - 1 + slides.length) % slides.length].url)} alt="" loading="lazy" />}
      </div>
      <div className="studio-story-frame" key={current.url + active}>
        {video && current.kind === 'promotions'
          ? <video controls preload="metadata" playsInline muted={Boolean(soundtrackVideo && soundEnabled)} src={backendUrl(current.url)} aria-label={current.title} onPlay={() => {if (!soundtrackVideo) audio.current?.pause()}} />
          : video && current.embed_url && safeEmbed(current.embed_url)
            ? playingVideo
              ? <iframe title={current.title} src={safeEmbed(current.embed_url)} allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen loading="lazy" />
              : <button className="studio-story-video-cover" type="button" onClick={() => {setPlayingVideo(true);audio.current?.pause()}}>
                <img src={backendUrl(current.url)} alt="" loading="lazy" />
                <span>▶ Play video</span>
              </button>
            : <img src={backendUrl(current.url)} alt={current.title} loading="lazy" decoding="async" />}
      </div>
      <div className="studio-story-neighbour studio-story-neighbour--next" aria-hidden="true">
        {['photos','flyers','activities','appearances'].includes(slides[(active + 1) % slides.length]?.kind) &&
          <img src={backendUrl(slides[(active + 1) % slides.length].url)} alt="" loading="lazy" />}
      </div>
    </div>
    <div className="studio-story-navigation">
      <button type="button" onClick={() => step(-1)} aria-label="Previous slide">←</button>
      <div className="studio-story-progress" role="group" aria-label="Choose slide">{slides.map((slide,i) =>
        <button type="button" key={i} aria-label={`Slide ${i + 1}: ${slide.title}`} aria-current={i === active ? 'step' : undefined}
          className={i === active ? 'active' : ''} onClick={() => setActive(i)} />)}</div>
      <button type="button" onClick={() => step(1)} aria-label="Next slide">→</button>
    </div>
    <div className="studio-story-copy"><h3>{story.title}</h3>{current.caption && <p className="studio-story-slide-caption">{current.caption}</p>}{story.description && <p>{story.description}</p>}</div>
    {story.audio_url && <div className="studio-story-audio">
      <audio ref={audio} src={backendUrl(story.audio_url)} preload="none" loop={story.loop_audio} onEnded={() => setSoundEnabled(false)} />
      <button type="button" onClick={() => {
        if (!audio.current) return
        if (soundEnabled) {audio.current.pause();setSoundEnabled(false)}
        else {setSoundEnabled(true); if(!video || soundtrackVideo) audio.current.play().catch(() => setSoundEnabled(false))}
      }} aria-pressed={soundEnabled}>{soundEnabled ? '♫ Turn soundtrack off' : '♫ Play optional soundtrack'}</button>
      <label>Volume <input type="range" min="0" max="1" step=".1" defaultValue=".65"
        onChange={e => {if (audio.current) audio.current.volume = Number(e.target.value)}} /></label>
    </div>}
  </article>
}

/** Each complete multimedia story consumes one publication slot. */
export default function PublishedCarousels({ destination }) {
  const [items, setItems] = useState([])
  const [status, setStatus] = useState('loading')
  useEffect(() => {
    const controller = new AbortController()
    setStatus('loading')
    fetch(`${api}/dic/studio/public-carousels/?destination=${encodeURIComponent(destination)}`,
      { credentials: 'omit', cache: 'no-store', signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('Unavailable'); return response.json() })
      .then(data => { if (!Array.isArray(data.items)) throw new Error('Invalid feed'); setItems(data.items); setStatus('ready') })
      .catch(error => { if (error.name !== 'AbortError') setStatus('unavailable') })
    return () => controller.abort()
  }, [destination])
  if (status !== 'ready' || !items.length) return null
  const scrapbook = destination === 'dic_memories'
  return <section className={`studio-stories studio-stories--${destination}`} aria-label={scrapbook ? 'Camp scrapbook stories' : 'Media stories'}>
    <Container>
      <header className="studio-stories-heading"><span>{scrapbook ? 'THE CAMP SCRAPBOOK' : 'THE DAWANA COLLECTION'}</span>
        <h2>{scrapbook ? 'Stories worth keeping' : 'Explore our stories'}</h2>
        <p>Swipe through each collection without leaving this page.</p>
      </header>
      <div className="studio-stories-scroll">{items.map(story => <Story key={story.id} story={story} />)}</div>
    </Container>
  </section>
}
