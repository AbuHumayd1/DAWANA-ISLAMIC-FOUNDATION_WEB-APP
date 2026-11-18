import { useEffect, useState } from 'react'
import { resolveMediaUrl } from '../../services/mediaUrl'

const apiBase = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

// Only the editorially published public showcase is used here. This does not
// expose unpublished camp timetables, staff notes, or camper-specific data.
export default function CamperApprovedActivities({ onNavigate }) {
  const [state, setState] = useState({ status: 'loading', activities: [] })
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${apiBase}/dic/showcase/`, { credentials: 'omit', cache: 'no-store', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Approved camp activities are temporarily unavailable.')
        const result = await response.json()
        if (!Array.isArray(result.activities)) throw new Error('Approved activities could not be displayed.')
        if (!controller.signal.aborted) setState({ status: 'ready', activities: result.activities })
      }).catch(error => {
        if (!controller.signal.aborted) setState({ status: 'error', activities: [], message: error.message })
      })
    return () => controller.abort()
  }, [])
  return <section className="cw-approved-activities" aria-label="Approved camp activities">
    <div className="cw-approved-heading"><span className="cp-kicker">DIC · EXPLORE</span><h1>Approved camp activities</h1>
      <p>Discover activities officially released for the camp. Your published daily programme is available separately in My Day.</p></div>
    {state.status === 'loading' && <p role="status">Loading approved camp activities…</p>}
    {state.status === 'error' && <p role="alert">{state.message}</p>}
    {state.status === 'ready' && !state.activities.length && <p role="status">No activities have been approved for public display yet. Check back after new camp announcements.</p>}
    {state.status === 'ready' && !!state.activities.length && <div className="cw-approved-grid">{state.activities.map(activity =>
      <article className="cw-approved-card" key={activity.id}>
        {activity.image_url && <img src={resolveMediaUrl(activity.image_url)} alt={activity.alt_text || ''} loading="lazy" />}
        <div className="cw-approved-card-copy">
          <small>{activity.category || 'Camp activity'}{activity.featured ? ' · Featured' : ''}</small>
          <h2>{activity.title}</h2>
          {activity.description && <p>{activity.description}</p>}
        </div>
      </article>
    )}</div>}
    <p className="cw-approved-note">Activities shown here are an approved showcase, not a guarantee of a particular day's timetable.</p>
    <div className="cw-approved-actions"><button type="button" onClick={() => onNavigate?.('day')}>Open My Day</button><button type="button" onClick={() => onNavigate?.('explore')}>Back to Explore</button></div>
  </section>
}
