import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'

export default function CampUpdates({ item }) {
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
  return <section className="cp-card"><h2>Camp announcements</h2><button onClick={() => setRevision(value => value + 1)}>Refresh announcements</button>
    {error && <p role="alert">{error}</p>}{!data && !error && <p role="status">Loading published announcements…</p>}
    {data && !data.announcements_ready && <p>Announcements are awaiting setup.</p>}
    {data?.announcements_ready && !data.announcements.length && <p>No published announcements for your camp edition.</p>}
    {data?.announcements.map(row => <article key={row.id}><h3>{row.title}</h3><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{row.body}</p></article>)}
  </section>
}
