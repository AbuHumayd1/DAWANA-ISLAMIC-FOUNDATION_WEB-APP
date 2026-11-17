import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { timetablePath } from '../../services/timetables'
import './Timetables.css'

export default function CamperTimetables({ item, initialType = 'activities' }) {
  const [type, setType] = useState(initialType === 'food' ? 'food' : 'activities'), [revision, setRevision] = useState(0)
  const [state, setState] = useState({ key: '', data: null, error: '' })
  const path = timetablePath(item, type), key = path + ':' + revision
  useEffect(() => {
    const timer = window.setInterval(() => setRevision(value => value + 1), 60000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    participantRequest(path, undefined, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ key, data, error: '' })
    }).catch(error => { if (!controller.signal.aborted) setState({ key, data: null, error: error.message }) })
    return () => controller.abort()
  }, [path, key])
  const data = state.key === key ? state.data : null, error = state.key === key ? state.error : ''
  return <section className={`dic-timetables cw-day ${type === 'food' ? 'cw-food' : ''}`} aria-label="Timetables">
    <div className="cw-day-tabs" role="group" aria-label="Timetable type"><button aria-pressed={type === 'activities'} onClick={() => { setType('activities') }}><span aria-hidden="true">☀</span>Daily Activities</button><button aria-pressed={type === 'food'} onClick={() => { setType('food') }}><span aria-hidden="true">♧</span>Food Timetable</button></div>
    {error && <p role="alert">{error}</p>}{!error && !data && <p role="status">Loading published timetable…</p>}
    {data && <>
      <div className="cw-day-heading"><div><span className="cp-kicker">{data.camp_state === 'upcoming' ? 'CAMP BEGINS 23 DECEMBER' : data.camp_state === 'completed' ? 'CAMP CONCLUDED' : 'YOUR DAY IS HERE'}</span><h2>{type === 'food' ? 'At the table' : 'Make today meaningful.'}</h2></div><span className="cw-day-chip">{data.entries.length > 0 ? `Day ${data.entries[0].day_number}` : data.camp_state === 'upcoming' ? 'Coming soon' : data.date}</span></div><p className="cp-section-note">Today: {data.today} · Africa/Lagos</p>
      {data.state !== 'published' ? <div className="cw-day-empty" role="status"><span aria-hidden="true">✧</span><h3>A little anticipation</h3><p>The daily programme and meals will appear automatically from 23 December 2026, changing each day in Lagos time.</p></div> : <ol className="tt-schedule cw-agenda">{data.entries.map((row,index) => <li key={row.id} className={`cw-agenda-item cw-agenda-tone-${index % 3} ${data.current === row.id ? 'tt-current' : ''}`}><div className="cw-agenda-time"><strong>{row.time_label}</strong><span aria-hidden="true">{type === 'food' ? '♧' : '✧'}</span></div><div className="cw-agenda-content">{data.current === row.id && <span className="cw-now">Current activity</span>}{data.upcoming === row.id && <span className="cw-now">Upcoming</span>}<h3>{row.description || 'Meal description not supplied in source.'}</h3>{row.location && <p>{row.location}</p>}{row.instructions && <small>{row.instructions}</small>}{row.certainty !== 'confirmed' && <small>Schedule subject to change</small>}</div></li>)}</ol>}
    </>}
  </section>
}
