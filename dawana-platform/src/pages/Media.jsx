import PublishedCarousels from '../components/media/PublishedCarousels'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero } from '../components/pages/PublicPage'
import MediaSubscribe from '../components/media/MediaSubscribe'
import { backendUrl } from '../services/productionContract'
import { hostedVideoThumbnail } from '../services/hostedVideoThumbnail'
import './MediaCollections.css'

const COLLECTIONS = [
  { id: 'videos', name: 'All Videos', detail: 'Foundation lectures, reminders and programme recordings.' },
  { id: 'audio', name: 'All Audio', detail: 'Publicly released audio lectures and reminders.' },
  { id: 'dic', name: 'Darul Islam Camp', detail: 'DIC videos and audio, organised by edition.' },
  { id: 'ramadan', name: 'Ramadan Tafseer', detail: 'Tafseer recordings by series and year.' },
  { id: 'shorts', name: 'Short Videos', detail: 'Short reminders, clips and excerpts.' },
  { id: 'other', name: 'Other Programmes', detail: 'Youth outreach and special programmes.' },
  { id: 'podcasts', name: 'Podcasts', detail: 'Shows and recorded episodes.' },
  { id: 'live', name: 'Live Broadcasts', detail: 'Upcoming and current live programmes.' },
  { id: 'publications', name: 'Articles & PDFs', detail: 'Research, reflections and documents.' },
  { id: 'events', name: 'Events', detail: 'Programme schedules and announcements.' },
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
  const thumbnail = hostedVideoThumbnail(embed)
  const [imageFailed, setImageFailed] = useState(false)
  const url = backendUrl(item.url)
  const audio = isAudio(item)
  return <article className="media-collection-entry">
    {audio ? <div className="media-collection-audio"><span aria-hidden="true">♫</span><audio controls preload="none" src={url} aria-label={'Listen to ' + item.title}/></div>
      : embed ? <div className="media-collection-screen">{playing ? <iframe title={item.title} src={embed} loading="lazy" allow="accelerometer; autoplay; encrypted-media; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin"/> : <button className="media-video-cover" type="button" onClick={() => setPlaying(true)} aria-label={'Play ' + item.title}>{thumbnail && !imageFailed && <img className="media-video-thumbnail" src={thumbnail} loading="lazy" alt="" onError={() => setImageFailed(true)} referrerPolicy="no-referrer"/>}<span className="media-video-play" aria-hidden="true">▶</span></button>}</div>
      : <div className="media-collection-screen"><video controls preload="none" src={url} aria-label={item.title}/></div>}
    <div className="media-collection-entry-copy">
      <span className="media-collection-type">{audio ? 'Audio recording' : 'Video'}{item.edition ? ' · ' + item.edition : ''}</span>
      <h3>{item.title}</h3>
      {item.lecturer && <p className="media-collection-speaker">{item.lecturer}</p>}
      {item.description && <p>{item.description}</p>}
      {item.event && ['other','ramadan'].includes(item.programme) && <small>{item.event}</small>}
      {audio ? <a href={url + '?download=1'}>Download audio</a> : embed ? <a href={embed} target="_blank" rel="noopener noreferrer">Watch video</a> : null}
    </div>
  </article>
}
function trustedMeetLink(value) {
  try {const url = new URL(value);return url.protocol === 'https:' && url.hostname === 'meet.google.com' && !url.username && !url.password && !url.port && !url.hash} catch {return false}
}
function EditorialMediaEntry({item}) {
  const embed = safeEmbed(item.embed_url)
  const isLive = item.kind === 'live'
  return <article className="media-collection-entry editorial-media-entry">
    <div className="media-collection-entry-copy">
      <span className="media-collection-type">{({article:'Article',document:'PDF publication',event:'Event',live:'Live broadcast',podcast:'Podcast',video:'Video'})[item.kind]}{item.kind==='podcast' ? ' · Season ' + item.season + ', episode ' + item.episode : ''}</span>
      <h3>{item.title}</h3>
      {item.description && <p>{item.description}</p>}
      {item.event_at && <p>{new Intl.DateTimeFormat('en-NG',{dateStyle:'full',timeStyle:'short',timeZone:'Africa/Lagos'}).format(new Date(item.event_at))} WAT</p>}
      {isLive && <strong className="media-live-status">{item.live_state === 'live' ? 'Live now' : item.live_state === 'ended' ? 'Broadcast ended' : 'Scheduled broadcast'}</strong>}
      {item.kind === 'article' && item.body && <div className="media-article-body">{item.body}</div>}
      {embed && <div className="media-collection-screen"><iframe title={item.title} loading="lazy" src={embed} allow="encrypted-media; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin"/></div>}
      {item.kind==='document' && item.document_url && <a href={backendUrl(item.document_url)}>Download PDF</a>}
      {trustedMeetLink(item.meeting_url) && <a href={item.meeting_url} target="_blank" rel="noopener noreferrer">Join Google Meet</a>}
      {embed && <a href={item.video_url} target="_blank" rel="noopener noreferrer">Open on video platform</a>}
    </div>
  </article>
}

export default function Media() {
  const [params, setParams] = useSearchParams()
  const [editorial, setEditorial] = useState({collections: [], items: [], status: 'loading', hasMore: false})
  const [editorialPage, setEditorialPage] = useState(1)
  const publicCollections = [...COLLECTIONS, ...editorial.collections.map(c => ({id: c.slug, name: c.title, detail: c.description || (c.kind === 'podcast' ? 'Podcast show' : 'Lecture collection')}))]
  const selected = publicCollections.some(row => row.id === params.get('collection')) ? params.get('collection') : 'videos'
  useEffect(() => {
    const controller = new AbortController()
    const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
    fetch(base + '/dic/studio/public-editorial/?page=' + editorialPage, {credentials: 'omit',cache: 'no-store',signal:controller.signal})
      .then(response => {if (!response.ok) throw new Error('New publications temporarily unavailable'); return response.json()})
      .then(data => setEditorial(previous => ({collections: data.collections || [], items: editorialPage === 1 ? data.items || [] : [...previous.items,...(data.items || [])], hasMore: Boolean(data.has_more), status:'ready'})))
      .catch(error => {if (error.name !== 'AbortError') setEditorial(previous => ({...previous,status:'error'}))})
    return () => controller.abort()
  }, [editorialPage])
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
  const selectedCollection = publicCollections.find(row => row.id === selected) || COLLECTIONS[0]
  const collectionById = new Map(editorial.collections.map(row => [row.id,row.slug]))
  const newItems = editorial.items.filter(item => {
    if (selected === 'videos') return ['video','podcast'].includes(item.kind)
    if (selected === 'podcasts') return item.kind === 'podcast'
    if (selected === 'live') return item.kind === 'live'
    if (selected === 'publications') return ['article','document'].includes(item.kind)
    if (selected === 'events') return item.kind === 'event'
    if (selected === 'other') return !item.collection_id
    return collectionById.get(item.collection_id) === selected
  })
  const collectionItems = items.filter(row => matches(row, selected))
    .filter(row => format === 'all' || format === 'videos' && isVideo(row) || format === 'audio' && isAudio(row))
  const visualItems = items.filter(row => ['photos', 'flyers', 'activities', 'appearances'].includes(row.source_kind))
  return <div className="public-page media-page media-clean-page">
    <PageHero eyebrow="Foundation Media" title="Media Library" description="Lectures, reminders and programme recordings — organised in one simple archive."/>
    <PublishedCarousels destination="foundation_archive" />
    <section className="media-clean-section"><Container>
      <MediaSubscribe />
      <div className="media-clean-intro"><h2>Explore the media library</h2></div>
      <nav className="media-clean-collections" aria-label="Media library collections">
        {publicCollections.map(row => <button type="button" key={row.id} aria-current={selected === row.id ? 'page' : undefined}
          onClick={() => choose(row.id)}><strong>{row.name}</strong><small>{row.detail}</small></button>)}
      </nav>
      <div className="media-clean-results" id="media-archive">
        <div className="media-clean-results-header"><div><h2>{selectedCollection.name}</h2><p>{selectedCollection.detail}</p></div>
          {['dic','ramadan','other'].includes(selected) && <div className="media-clean-format" role="group" aria-label="Filter collection format">
            {['all','videos','audio'].map(value => <button key={value} type="button" aria-pressed={format === value}
              onClick={() => setFormat(value)}>{value === 'all' ? 'All formats' : value === 'audio' ? 'Audio' : 'Videos'}</button>)}
          </div>}
        </div>
        {(collectionItems.length > 0 || newItems.length > 0) ? <div className="media-clean-grid">{collectionItems.map((item,i) => <MediaEntry key={item.url + i} item={item}/>)}{newItems.map(item => <EditorialMediaEntry key={'editorial-' + item.id} item={item}/>)}</div>
          : status === 'loading' ? <p className="media-clean-empty" role="status">Loading approved publications…</p>
          : status === 'error' ? <p className="media-clean-empty" role="alert">The media archive is temporarily unavailable. Please refresh to try again.</p>
          : <p className="media-clean-empty">No published {selectedCollection.name.toLowerCase()} yet. Approved recordings will appear here when available.</p>}
        {status === 'error' && items.length > 0 && <p role="alert">Could not load more media. Please retry.</p>}
        {editorial.hasMore && <button className="media-clean-more" type="button" onClick={() => setEditorialPage(v => v + 1)}>Load more publications</button>}
        {hasMore && <button className="media-clean-more" type="button" disabled={status === 'loading'} onClick={() => setPage(value => value + 1)}>{status === 'loading' ? 'Loading…' : 'Load more media'}</button>}
      </div>
      {visualItems.length > 0 && <section className="media-clean-visuals" aria-label="Published photographs and visuals">
        <div className="media-clean-results-header"><div><span className="eyebrow">Photography</span><h2>Photo gallery</h2></div></div>
        <div className="media-clean-visual-grid">{visualItems.map((item, index) => <a key={item.url + index} href={backendUrl(item.url)} target="_blank" rel="noopener noreferrer">
          <img src={backendUrl(item.url)} loading="lazy" alt={item.title}/><span>{item.title}</span>
        </a>)}</div>
      </section>}
    </Container></section>
  </div>
}
