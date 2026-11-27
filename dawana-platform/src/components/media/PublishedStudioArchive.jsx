import { useEffect, useId, useRef, useState } from 'react'
import { backendUrl } from '../../services/productionContract'
import { hostedVideoThumbnail } from '../../services/hostedVideoThumbnail'
import { Container } from '../layout/SiteChrome'
import './PublishedStudioArchive.css'
import MediaGlide from './MediaGlide'

function HostedVideoCover({item, active, onPlay, embed}) {
  const [failed, setFailed] = useState(false)
  const thumbnail = hostedVideoThumbnail(embed)
  return <div className="published-studio-visual published-studio-video">
    {active ? <iframe title={item.title} src={embed} loading="lazy" allow="accelerometer; autoplay; encrypted-media; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin"/> :
      <button className="published-studio-video-cover" type="button" onClick={onPlay} aria-label={`Play ${item.title} on this page`}>
        {thumbnail && !failed && <img src={thumbnail} alt="" loading="lazy" onError={() => setFailed(true)} referrerPolicy="no-referrer" />}
        <span className="published-studio-play" aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" focusable="false"><path d="M8 5.5v13l11-6.5z" /></svg></span>
      </button>}
  </div>
}
function approvedVideoLink(value) {
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'https:' &&
      ['www.youtube-nocookie.com', 'player.vimeo.com'].includes(parsed.hostname) &&
      !parsed.username && !parsed.password && !parsed.hash && !parsed.port
      ? parsed.href : ''
  } catch { return '' }
}

/** Public only: the backend checks both current source publication and destination. */
export default function PublishedStudioArchive({ destination = 'foundation_archive' }) {
  const headingId = useId()
  const isHighlight = destination === 'foundation_home' || destination === 'dic_landing'
  const [items, setItems] = useState([])
  const [state, setState] = useState('loading')
  const [activeEmbed, setActiveEmbed] = useState('')
  const [activeAlbum, setActiveAlbum] = useState('')
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [pageError, setPageError] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [retry, setRetry] = useState(0)
  const [openStory, setOpenStory] = useState(null)
  const storyCloseRef = useRef(null)
  const storyTriggerRef = useRef(null)
  useEffect(() => { setPage(1); setItems([]); setHasMore(false); setState('loading'); setOpenStory(null) }, [destination])
  useEffect(() => {
    if (!openStory) return undefined
    storyCloseRef.current?.focus()
    function dismiss(event) { if (event.key === 'Escape') setOpenStory(null) }
    document.addEventListener('keydown', dismiss)
    return () => {
      document.removeEventListener('keydown', dismiss)
      storyTriggerRef.current?.focus()
    }
  }, [openStory])
  function showStory(item, event) {
    storyTriggerRef.current = event.currentTarget
    setOpenStory(item)
  }
  useEffect(() => {
    const controller = new AbortController()
    if (page === 1) { setActiveEmbed(''); setActiveAlbum(''); setState('loading') }
    else setLoadingMore(true)
    setPageError(false)
    const api = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
    fetch(`${api}/dic/studio/public-placements/?destination=${encodeURIComponent(destination)}&page=${page}${destination === 'foundation_home' ? '&view=editorial' : ''}`, {
      credentials: 'omit', cache: 'no-store', signal: controller.signal,
    }).then(async response => {
      if (!response.ok) throw new Error('Archive unavailable')
      return response.json()
    }).then(data => {
      if (!Array.isArray(data.items)) throw new Error('Archive unavailable')
      const accepted = data.items.filter(row =>
        // Safeguard while already-published legacy flyer placements are retired.
        !(destination === 'dic_landing' && row.source_kind === 'flyers') &&
        !(destination === 'foundation_home' && row.source_kind === 'photos') &&
        typeof row.title === 'string' && typeof row.url === 'string' &&
        ((row.url.startsWith('/api/v1/dic/') && row.url.length < 400) ||
         (row.source_kind === 'hosted' && !!approvedVideoLink(row.embed_url))))
      setItems(previous => page === 1 ? accepted : [...previous, ...accepted])
      setHasMore(data.has_more === true && page < 100)
      setState('ready')
      setLoadingMore(false)
    }).catch(error => { if (error.name !== 'AbortError') { if (page === 1) setState('unavailable'); else setPageError(true); setLoadingMore(false) } })
    return () => controller.abort()
  }, [destination, page, retry])
  if (state !== 'ready' || (!items.length && !hasMore)) return null
  const albums = [...new Set(items.filter(item => item.source_kind === 'photos' && item.album).map(item => item.album))].sort()
  const visibleItems = (activeAlbum ? items.filter(item => item.source_kind === 'photos' && item.album === activeAlbum) : items)
    .slice(0, destination === 'foundation_home' ? 3 : destination === 'dic_landing' ? 4 : undefined)
  const canBrowseAlbums = ['foundation_archive', 'dic_memories'].includes(destination) && albums.length > 0
  return <section className={`published-studio-archive published-studio-archive--${destination}`} aria-labelledby={headingId}><Container>
    <div className="published-studio-heading">
      {destination === 'foundation_home' && <span className="published-studio-eyebrow">THE DAWANA JOURNAL</span>}
      <h2 id={headingId}>{destination === 'foundation_home' ? 'Stories worth sharing' : destination === 'dic_landing' ? 'DIC media highlights' : destination === 'dic_memories' ? 'Camp memories' : 'Media library'}</h2>
      {destination === 'foundation_home' && <a className="published-studio-heading-link" href="/media">Explore the library <span aria-hidden="true">↗</span></a>}
    </div>
    {canBrowseAlbums && <nav className="published-studio-albums" aria-label="Browse photo albums"><button type="button" aria-pressed={!activeAlbum} onClick={() => setActiveAlbum('')}>All publications</button>{albums.map(album => <button type="button" key={album} aria-pressed={activeAlbum === album} onClick={() => setActiveAlbum(album)}>{album}</button>)}</nav>}
    <MediaGlide className="published-studio-grid" count={visibleItems.length} label="Publications" auto={isHighlight && !openStory && !activeEmbed}>{visibleItems.map((item, i) => <article key={item.url + i} className={`published-studio-card${destination === 'foundation_home' && i === 0 ? ' published-studio-card--lead' : ''}`}>
      {item.playback_url?.startsWith('/api/v1/dic/') ? <div className="published-studio-visual published-studio-video"><video controls preload="none" playsInline src={backendUrl(item.playback_url)} poster={item.poster_url?.startsWith('/api/v1/dic/') ? backendUrl(item.poster_url) : undefined} aria-label={item.title} style={{width:'100%',height:'100%',objectFit:'contain'}}/></div> : item.source_kind === 'hosted' && approvedVideoLink(item.embed_url) ? <HostedVideoCover item={item} embed={approvedVideoLink(item.embed_url)} active={activeEmbed === item.url} onPlay={() => setActiveEmbed(item.url)} /> : ['photos', 'flyers', 'promotions', 'activities', 'videos', 'appearances'].includes(item.source_kind) && <div className="published-studio-visual published-studio-visual--original-ratio">
        {item.source_kind === 'promotions' ? <span aria-hidden="true">▶</span> :
          <img loading="lazy" src={backendUrl(item.url)} alt={item.title} />}
      </div>}
      <div className="published-studio-content"><span>{['hosted', 'videos'].includes(item.source_kind) ? 'Video lecture' : item.source_kind.replaceAll('_',' ')}</span><h3>{item.title}</h3>{item.description && (isHighlight
        ? <button className="published-studio-story-action" type="button" onClick={event => showStory(item, event)}>Read story <span aria-hidden="true">↗</span></button>
        : item.description.length > 340
          ? <details className="published-studio-long-caption"><summary>Read full caption</summary><p>{item.description}</p></details>
          : <p className="published-studio-caption">{item.description}</p>)}
      {(item.playback_url || item.source_kind === 'hosted' || item.source_kind !== 'videos' || approvedVideoLink(item.embed_url)) ?
        <a href={item.playback_url?.startsWith('/api/v1/dic/') ? backendUrl(item.playback_url) : ['hosted', 'videos'].includes(item.source_kind) ? approvedVideoLink(item.embed_url) : backendUrl(item.url)} target="_blank" rel="noopener noreferrer">{['promotions', 'videos', 'hosted'].includes(item.source_kind) ? 'Watch publication' : 'View publication'}</a> : null}</div>
    </article>)}</MediaGlide>
    {pageError && <p role="alert">Could not load more publications. You can retry.</p>}
    {isHighlight && <a className="published-studio-load-more published-studio-home-cta" href="/media">Discover more publications <span aria-hidden="true">↗</span></a>}
    {isHighlight && openStory && <div className="published-studio-story-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setOpenStory(null) }}>
      <section role="dialog" aria-modal="true" aria-label={`Publication: ${openStory.title}`} className="published-studio-story-dialog">
        <div className="published-studio-story-header"><div><span>{destination === 'dic_landing' ? 'DIC MEDIA HIGHLIGHTS' : 'DAWANA JOURNAL'}</span><h3>{openStory.title}</h3></div><button ref={storyCloseRef} type="button" onClick={() => setOpenStory(null)} aria-label="Close publication">✕</button></div>
        <div className="published-studio-story-body"><p>{openStory.description}</p></div>
        <div className="published-studio-story-footer"><button type="button" onClick={() => setOpenStory(null)}>Close story</button></div>
      </section>
    </div>}
    {destination !== 'foundation_home' && destination !== 'dic_landing' && hasMore && <button type="button" className="published-studio-load-more" onClick={() => pageError ? setRetry(n => n + 1) : setPage(n => n + 1)} disabled={loadingMore || page >= 100}>{loadingMore ? 'Loading approved media…' : pageError ? 'Retry this page' : 'Load more approved media'}</button>}
  </Container></section>
}
