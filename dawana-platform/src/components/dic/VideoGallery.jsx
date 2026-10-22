import { useEffect, useRef, useState } from 'react'
import { Container } from '../layout/SiteChrome'
import './VideoGallery.css'
import { safeVideoEmbed } from '../../services/videoPlayback'

const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')


export default function VideoGallery() {
  const [videos, setVideos] = useState([])
  const [status, setStatus] = useState('loading')
  const [edition, setEdition] = useState('')
  const [activity, setActivity] = useState('')
  const [selected, setSelected] = useState(null)
  const [playback, setPlayback] = useState(null)
  const [playbackState, setPlaybackState] = useState('loading')
  const dialog = useRef(null)
  const opener = useRef(null)
  const open = selected !== null

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${base}/dic/videos/`, { credentials: 'omit', cache: 'no-store', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Video archive unavailable')
        const data = await response.json()
        if (!Array.isArray(data.videos)) throw new Error('Invalid archive')
        setVideos(data.videos)
        setStatus('ready')
      }).catch(error => { if (error.name !== 'AbortError') setStatus('error') })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const node = dialog.current
    node.showModal()
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { node.close(); document.body.style.overflow = overflow; opener.current?.focus() }
  }, [open])

  useEffect(() => {
    if (selected === null) return undefined
    const controller = new AbortController()
    fetch(`${base}/dic/videos/${encodeURIComponent(selected)}/playback/`, { credentials: 'omit', cache: 'no-store', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Video unavailable')
        const source = await response.json()
        const url = safeVideoEmbed(source)
        if (!url) throw new Error('Unapproved player')
        if (controller.signal.aborted) return
        setPlayback({ id: selected, url })
        setPlaybackState('ready')
      }).catch(error => { if (error.name !== 'AbortError') setPlaybackState('error') })
    return () => controller.abort()
  }, [selected])

  const visible = videos.filter(video => (!edition || String(video.edition.id) === edition) && (!activity || video.activities.some(tag => String(tag.id) === activity)))
  const current = visible.find(video => video.id === selected)
  const editions = [...new Map(videos.map(video => [String(video.edition.id), video.edition.name])).entries()]
  const activities = [...new Map(videos.flatMap(video => video.activities.map(tag => [String(tag.id), tag.name]))).entries()]
  const select = id => { setPlayback(null); setPlaybackState('loading'); setSelected(id) }
  const move = direction => select(visible[(visible.findIndex(video => video.id === selected) + direction + visible.length) % visible.length].id)
  const close = () => { setSelected(null); setPlayback(null) }
  const keyboard = event => {
    if (event.key === 'Tab') {
      const controls = [...event.currentTarget.querySelectorAll('button:not([disabled]), iframe')]
      if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls.at(-1)?.focus() }
      else if (!event.shiftKey && document.activeElement === controls.at(-1)) { event.preventDefault(); controls[0]?.focus() }
    }
    if (current && event.key === 'ArrowRight') { event.preventDefault(); move(1) }
    if (current && event.key === 'ArrowLeft') { event.preventDefault(); move(-1) }
  }

  return <section className="dic-videos" aria-labelledby="dic-videos-title"><Container>
    <div className="video-heading"><span className="eyebrow">THE CAMP FILM ARCHIVE</span><h2 id="dic-videos-title">Press play. Look back.</h2><p>Approved recordings and highlights from past camp editions.</p></div>
    {status === 'loading' && <p role="status">Opening the video archive…</p>}
    {status === 'error' && <p role="status">The video archive is temporarily unavailable. Please visit again later.</p>}
    {status === 'ready' && !videos.length && <div className="video-empty"><span aria-hidden="true">▷</span><h3>The next story is on its way</h3><p>Approved camp recordings will appear here when they are available.</p></div>}
    {!!videos.length && <>
      <div className="video-filters"><label>Camp edition<select aria-label="Video camp edition" value={edition} onChange={event => setEdition(event.target.value)}><option value="">All editions</option>{editions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label><label>Activity<select aria-label="Video activity" value={activity} onChange={event => setActivity(event.target.value)}><option value="">All activities</option>{activities.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label><p role="status">{visible.length} {visible.length === 1 ? 'video' : 'videos'}</p></div>
      <div className="video-grid">{visible.map(video => <article className={`video-card${video.featured ? ' video-featured' : ''}`} key={video.id}><button type="button" aria-label={`Play video: ${video.caption}`} onClick={event => { opener.current = event.currentTarget; select(video.id) }}><span className="video-poster"><img src={video.thumbnail_url} alt={video.alt_text} loading="lazy" decoding="async" width="960" height="540" /><span className="video-play" aria-hidden="true">▶</span><span className="video-provider">{video.provider === 'youtube' ? 'YouTube' : 'Vimeo'}</span></span><span className="video-copy"><small>{video.edition.name}{video.featured ? ' · Featured recording' : ''}</small><strong>{video.caption}</strong><span>{video.activities.map(tag => tag.name).join(' · ')}</span></span></button></article>)}</div>
      {!visible.length && <p>No approved videos match these filters.</p>}
    </>}
    <dialog ref={dialog} className="video-viewer" aria-labelledby="video-viewer-title" onCancel={close} onKeyDown={keyboard} onClick={event => { if (event.target === event.currentTarget) close() }}>
      <button type="button" className="video-close" aria-label="Close video viewer" autoFocus onClick={close}>Close ×</button>
      {current && <div className="video-stage"><h3 id="video-viewer-title">{current.caption}</h3><p>{current.edition.name} · Playback connects to {current.provider === 'youtube' ? 'YouTube' : 'Vimeo'}.</p>
        {playbackState === 'loading' && <p role="status">Preparing the player…</p>}
        {playbackState === 'error' && <p role="alert">This recording is currently unavailable. Please close the viewer and try again later.</p>}
        {playback?.id === selected && <iframe key={selected} className="video-frame" src={playback.url} title={current.caption} allow="fullscreen; picture-in-picture; encrypted-media" sandbox="allow-scripts allow-same-origin allow-presentation" referrerPolicy="strict-origin-when-cross-origin" allowFullScreen />}
        <div className="video-controls"><button type="button" disabled={visible.length < 2} onClick={() => move(-1)}>← Previous video</button><button type="button" disabled={visible.length < 2} onClick={() => move(1)}>Next video →</button></div>
      </div>}
    </dialog>
  </Container></section>
}
