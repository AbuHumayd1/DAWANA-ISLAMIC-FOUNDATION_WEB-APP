import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'

export default function CampUpdates({ item, compact = false, onReadMore }) {
  const [state, setState] = useState({ key: null, data: null, error: '' }), [revision, setRevision] = useState(0)
  const key = item + ':' + revision
  useEffect(() => {
    const controller = new AbortController()
    participantRequest('/camp-updates/?item_id=' + encodeURIComponent(item), undefined, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ key, data, error: '' }) })
      .catch(error => { if (!controller.signal.aborted) setState({ key, data: null, error: error.message }) })
    return () => controller.abort()
  }, [item, key])
  const data = state.key === key ? state.data : null, error = state.key === key ? state.error : ''
  return <section className="cp-card cp-announcements"><div className="cp-card-title"><div><span className="cp-kicker">GOOD TO KNOW</span><h2>Camp announcements</h2></div>{compact ? <button onClick={onReadMore}>Read more ↗</button> : <button onClick={() => setRevision(value => value + 1)}>Refresh announcements</button>}</div>
    {error && <p role="alert">{error}</p>}{!data && !error && <p role="status">Loading published announcements…</p>}
    {data && !data.announcements_ready && <p>Announcements are awaiting setup.</p>}
    {data?.announcements_ready && !data.announcements.length && <p>No published announcements for your camp edition.</p>}
    {(compact ? data?.announcements.slice(0, 2) : data?.announcements)?.map(row => <article key={row.id}><span className="cp-announcement-dot" aria-hidden="true" /><div><h3>{row.title}</h3><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{compact && row.body.length > 180 ? row.body.slice(0, 180) + '…' : row.body}</p></div></article>)}
  </section>
}
