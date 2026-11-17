import { useEffect, useState } from 'react'
import { backendUrl } from '../services/productionContract'
import { Container } from '../components/layout/SiteChrome'
import './PublishedStudioArchive.css'

/** Public only: the backend checks both current source publication and destination. */
export default function PublishedStudioArchive({ destination = 'foundation_archive' }) {
  const [items, setItems] = useState([])
  const [state, setState] = useState('loading')
  useEffect(() => {
    const controller = new AbortController()
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
        row.url.startsWith('/api/v1/dic/') && row.url.length < 400))
      setState('ready')
    }).catch(error => { if (error.name !== 'AbortError') setState('unavailable') })
    return () => controller.abort()
  }, [destination])
  if (state !== 'ready' || !items.length) return null
  return <section className="published-studio-archive" aria-labelledby="published-studio-title"><Container>
    <div className="published-studio-heading"><span className="eyebrow">Official publications</span><h2 id="published-studio-title">{destination === 'foundation_home' ? 'Featured Foundation stories' : destination === 'dic_landing' ? 'Official DIC media highlights' : destination === 'dic_memories' ? 'Selected camp memories' : 'From the DAWANA media library'}</h2><p>Approved media shared by our Foundation team.</p></div>
    <div className="published-studio-grid">{items.map((item, i) => <article key={item.url + i} className="published-studio-card">
      {['photos', 'flyers', 'promotions', 'activities'].includes(item.source_kind) && <div className="published-studio-visual">
        {item.source_kind === 'promotions' ? <span aria-hidden="true">▶</span> :
          <img loading="lazy" src={backendUrl(item.url)} alt={item.title} />}
      </div>}
      <div className="published-studio-content"><span>{item.source_kind.replaceAll('_',' ')}</span><h3>{item.title}</h3>{item.description && <p>{item.description}</p>}
      <a href={backendUrl(item.url)} target="_blank" rel="noopener noreferrer">{item.source_kind === 'promotions' ? 'Watch publication' : 'View publication'}</a></div>
    </article>)}</div>
  </Container></section>
}
