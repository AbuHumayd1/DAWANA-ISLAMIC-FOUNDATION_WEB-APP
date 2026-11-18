import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero } from '../components/pages/PublicPage'
import { backendUrl } from '../services/productionContract'
import './MediaCollections.css'

const COLLECTIONS = [
  { id: 'videos', name: 'All Videos', detail: 'Foundation lectures, reminders and programme recordings.' },
  { id: 'audio', name: 'All Audio', detail: 'Publicly released audio lectures and reminders.' },
  { id: 'dic', name: 'Darul Islam Camp', detail: 'DIC videos and audio, organised by edition.' },
  { id: 'ramadan', name: 'Ramadan Tafseer', detail: 'Tafseer recordings by series and year.' },
  { id: 'shorts', name: 'Short Videos', detail: 'Short reminders, clips and excerpts.' },
  { id: 'other', name: 'Other Programmes', detail: 'Podcasts, youth outreach, picnics and special events.' },
]
const isVideo = item => ['hosted', 'videos', 'promotions'].includes(item.source_kind)
const isAudio = item => item.source_kind === 'recordings'
function matches(item, category) {
  if (category === 'videos') return isVideo(item)
  if (category === 'audio') return isAudio(item)
  if (category === 'shorts') return isVideo(item) && item.programme === 'shorts'
  return item.programme === category && (isVideo(item) || isAudio(item))
}
function safeEmbed(value) {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && ['www.youtube-nocookie.com','player.vimeo.com'].includes(url.hostname)
      && !url.username && !url.password && !url.hash && !url.port ? url.href : ''
  } catch { return '' }
}
function MediaEntry({item}) {
  const [playing, setPlaying] = useState(false)
  const embed = safeEmbed(item.embed_url)
  const url = backendUrl(item.url)
  const audio = isAudio(item)
  return <article className="media-collection-entry">
    {audio ? <div className="media-collection-audio"><span aria-hidden="true">♫</span><audio controls preload="none" src={url} aria-label={'Listen to ' + item.title}/></div>
      : embed ? <div className="media-collection-screen">{playing ? <iframe title={item.title} src={embed} loading="lazy" allow="accelerometer; autoplay; encrypted-media; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin"/> : <button type="button" onClick={() => setPlaying(true)} aria-label={'Play ' + item.title}><span aria-hidden="true">▶</span> Play video</button>}</div>
      : <div className="media-collection-screen"><video controls preload="none" src={url} aria-label={item.title}/></div>}
    <div className="media-collection-entry-copy">
      <span className="media-collection-type">{audio ? 'Audio recording' : 'Video'}{item.edition ? ' · ' + item.edition : ''}</span>
      <h3>{item.title}</h3>
      {item.description && <p>{item.description}</p>}
      {item.event && ['other','ramadan'].includes(item.programme) && <small>{item.event}</small>}
      {audio ? <a href={url + '?download=1'}>Download audio</a> : embed ? <a href={embed} target="_blank" rel="noopener noreferrer">Watch video</a> : null}
    </div>
  </article>
}
export default function Media() {
  const [params, setParams] = useSearchParams()
  const selected = COLLECTIONS.some(row => row.id === params.get('collection')) ? params.get('collection') : 'videos'
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [status, setStatus] = useState('loading')
  const [format, setFormat] = useState('all')
  useEffect(() => {
    const controller = new AbortController()
    setStatus('loading')
    const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
    fetch(base + '/dic/studio/public-placements/?destination=foundation_archive&page=' + page, {
      credentials: 'omit', cache: 'no-store', signal: controller.signal,
    }).then(response => {
      if (!response.ok) throw new Error('Archive unavailable')
      return response.json()
    }).then(data => {
      if (!Array.isArray(data.items)) throw new Error('Archive unavailable')
      setItems(previous => page === 1 ? data.items : [...previous, ...data.items])
      setHasMore(Boolean(data.has_more) && page < 100)
      setStatus('ready')
    }).catch(error => {
      if (error.name !== 'AbortError') setStatus('error')
    })
    return () => controller.abort()
  }, [page])
  function choose(id) {
    const next = new URLSearchParams(params)
    next.set('collection', id)
    setParams(next)
    setFormat('all')
  }
  const selectedCollection = COLLECTIONS.find(row => row.id === selected)
  const collectionItems = items.filter(row => matches(row, selected))
    .filter(row => format === 'all' || format === 'videos' && isVideo(row) || format === 'audio' && isAudio(row))
  return <div className="public-page media-page media-clean-page">
    <PageHero eyebrow="Foundation Media" title="Media Library" description="Lectures, reminders and programme recordings — organised in one simple archive."/>
    <section className="media-clean-section"><Container>
      <div className="media-clean-intro"><span className="eyebrow">Explore the archive</span><h2>Find what you want to watch or listen to.</h2><p>Choose a collection. A recording may appear in both the general archive and its programme collection.</p></div>
      <nav className="media-clean-collections" aria-label="Media library collections">
        {COLLECTIONS.map(row => <button type="button" key={row.id} aria-current={selected === row.id ? 'page' : undefined}
          onClick={() => choose(row.id)}><strong>{row.name}</strong><small>{row.detail}</small></button>)}
      </nav>
      <div className="media-clean-results" id="media-archive">
        <div className="media-clean-results-header"><div><span className="eyebrow">Official publications</span><h2>{selectedCollection.name}</h2><p>{selectedCollection.detail}</p></div>
          {['dic','ramadan','other'].includes(selected) && <div className="media-clean-format" role="group" aria-label="Filter collection format">
            {['all','videos','audio'].map(value => <button key={value} type="button" aria-pressed={format === value}
              onClick={() => setFormat(value)}>{value === 'all' ? 'All formats' : value === 'audio' ? 'Audio' : 'Videos'}</button>)}
          </div>}
        </div>
        {collectionItems.length ? <div className="media-clean-grid">{collectionItems.map((item,i) => <MediaEntry key={item.url + i} item={item}/>)}</div>
          : status === 'loading' ? <p className="media-clean-empty" role="status">Loading approved publications…</p>
          : status === 'error' ? <p className="media-clean-empty" role="alert">The media archive is temporarily unavailable. Please refresh to try again.</p>
          : <p className="media-clean-empty">No published {selectedCollection.name.toLowerCase()} yet. Approved recordings will appear here when available.</p>}
        {status === 'error' && items.length > 0 && <p role="alert">Could not load more media. Please retry.</p>}
        {hasMore && <button className="media-clean-more" type="button" disabled={status === 'loading'} onClick={() => setPage(value => value + 1)}>{status === 'loading' ? 'Loading…' : 'Load more media'}</button>}
      </div>
    </Container></section>
  </div>
}
