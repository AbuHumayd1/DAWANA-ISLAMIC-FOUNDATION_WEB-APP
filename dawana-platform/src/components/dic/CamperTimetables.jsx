import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { adjacentDate, timetablePath } from '../../services/timetables'
import './Timetables.css'

export default function CamperTimetables({ item }) {
  const [type, setType] = useState('activities'), [day, setDay] = useState(''), [revision, setRevision] = useState(0)
  const [state, setState] = useState({ key: '', data: null, error: '' })
  const path = timetablePath(item, type, day), key = path + ':' + revision
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
  const previous = data && adjacentDate(data.dates, data.date, -1), next = data && adjacentDate(data.dates, data.date, 1)
  return <section className="cp-card dic-timetables"><h1>Timetables</h1>
    <div className="tt-controls"><label>Timetable<select value={type} onChange={event => { setType(event.target.value); setDay('') }}><option value="activities">Daily Activities</option><option value="food">Food Timetable</option></select></label><button type="button" onClick={() => setRevision(value => value + 1)}>Refresh</button></div>
    {error && <p role="alert">{error}</p>}{!error && !data && <p role="status">Loading published timetable…</p>}
    {data && <><h2>{data.edition_name} · {type === 'food' ? 'Food Timetable' : 'Daily Activities'}</h2><p>Today: {data.today} · Africa/Lagos</p>
      <div className="tt-controls"><button disabled={!previous} onClick={() => setDay(previous)}>Previous day</button><label>Camp date<select value={data.date} onChange={event => setDay(event.target.value)}>{data.dates.map(row => <option key={row.date} value={row.date}>{row.date}{row.published ? '' : ' · Not published'}</option>)}</select></label><button disabled={!next} onClick={() => setDay(next)}>Next day</button><button onClick={() => setDay('')}>Today / next published</button><button onClick={() => window.print()}>Print this day</button></div>
      <h3>{data.date}{data.entries.length > 0 && ` · Day ${data.entries[0].day_number}`}</h3>
      {data.state !== 'published' ? <p role="status">This day’s timetable has not been published. Please check again later.</p> : <ol className="tt-schedule">{data.entries.map(row => <li key={row.id} className={data.current === row.id ? 'tt-current' : ''}><div><strong>{row.time_label}</strong>{data.current === row.id && <span> · Current activity</span>}{data.upcoming === row.id && <span> · Upcoming</span>}</div><p>{row.description || 'Meal description not supplied in source.'}</p>{row.certainty === 'proposed' && <small>Proposed</small>}{row.location && <p>{row.location}</p>}{row.instructions && <small>{row.instructions}</small>}</li>)}</ol>}
    </>}
  </section>
}
