import { useEffect, useId, useState } from 'react'
import { backendUrl } from '../../services/productionContract'
import { Container } from '../layout/SiteChrome'
import './PublishedStudioArchive.css'

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
  const [items, setItems] = useState([])
  const [state, setState] = useState('loading')
  const [activeEmbed, setActiveEmbed] = useState('')
  const [activeAlbum, setActiveAlbum] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setActiveEmbed('')
    setActiveAlbum('')
    setState('loading')
    const api = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
    fetch(`${api}/dic/studio/public-placements/?destination=${encodeURIComponent(destination)}`, {
      credentials: 'omit', cache: 'no-store', signal: controller.signal,
    }).then(async response => {
      if (!response.ok) throw new Error('Archive unavailable')
      return response.json()
    }).then(data => {
      if (!Array.isArray(data.items)) throw new Error('Archive unavailable')
      setItems(data.items.filter(row =>
        typeof row.title === 'string' && typeof row.url === 'string' &&
        ((row.url.startsWith('/api/v1/dic/') && row.url.length < 400) ||
         (row.source_kind === 'hosted' && !!approvedVideoLink(row.embed_url)))))
      setState('ready')
    }).catch(error => { if (error.name !== 'AbortError') setState('unavailable') })
    return () => controller.abort()
  }, [destination])
  if (state !== 'ready' || !items.length) return null
  const albums = [...new Set(items.filter(item => item.source_kind === 'photos' && item.album).map(item => item.album))].sort()
  const visibleItems = activeAlbum ? items.filter(item => item.source_kind === 'photos' && item.album === activeAlbum) : items
  const canBrowseAlbums = ['foundation_archive', 'dic_memories'].includes(destination) && albums.length > 0
  return <section className="published-studio-archive" aria-labelledby={headingId}><Container>
    <div className="published-studio-heading"><span className="eyebrow">Official publications</span><h2 id={headingId}>{destination === 'foundation_home' ? 'Featured Foundation stories' : destination === 'dic_landing' ? 'Official DIC media highlights' : destination === 'dic_memories' ? 'Selected camp memories' : 'From the DAWANA media library'}</h2><p>Approved media shared by our Foundation team.</p></div>
    {canBrowseAlbums && <nav className="published-studio-albums" aria-label="Browse photo albums"><button type="button" aria-pressed={!activeAlbum} onClick={() => setActiveAlbum('')}>All publications</button>{albums.map(album => <button type="button" key={album} aria-pressed={activeAlbum === album} onClick={() => setActiveAlbum(album)}>{album}</button>)}</nav>}
    <div className="published-studio-grid">{visibleItems.map((item, i) => <article key={item.url + i} className="published-studio-card">
      {item.source_kind === 'hosted' && approvedVideoLink(item.embed_url) ? <div className="published-studio-visual published-studio-video">
        {activeEmbed === item.url ? <iframe title={item.title} src={approvedVideoLink(item.embed_url)} loading="lazy" allow="accelerometer; autoplay; encrypted-media; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" /> :
          <button type="button" onClick={() => setActiveEmbed(item.url)} aria-label={`Play ${item.title} on this page`}><span aria-hidden="true">▶</span>Play YouTube video or livestream</button>}
      </div> : ['photos', 'flyers', 'promotions', 'activities', 'videos', 'appearances'].includes(item.source_kind) && <div className="published-studio-visual">
        {item.source_kind === 'promotions' ? <span aria-hidden="true">▶</span> :
          <img loading="lazy" src={backendUrl(item.url)} alt={item.title} />}
      </div>}
      <div className="published-studio-content"><span>{item.source_kind.replaceAll('_',' ')}</span><h3>{item.title}</h3>{item.description && <p>{item.description}</p>}
      {(item.source_kind === 'hosted' || item.source_kind !== 'videos' || approvedVideoLink(item.embed_url)) ?
        <a href={['hosted', 'videos'].includes(item.source_kind) ? approvedVideoLink(item.embed_url) : backendUrl(item.url)} target="_blank" rel="noopener noreferrer">{['promotions', 'videos', 'hosted'].includes(item.source_kind) ? 'Watch publication' : 'View publication'}</a> : null}</div>
    </article>)}</div>
  </Container></section>
}
