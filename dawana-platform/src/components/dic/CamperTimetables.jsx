import CamperSelect from './CamperSelect'
import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { adjacentDate, timetablePath } from '../../services/timetables'
import { campDate } from '../../services/dicPresentation'
import './Timetables.css'

export default function CamperTimetables({ item, initialType = 'activities' }) {
  const [type, setType] = useState(initialType === 'food' ? 'food' : 'activities'), [day, setDay] = useState(''), [revision, setRevision] = useState(0)
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
  return <section className={`dic-timetables cw-day ${type === 'food' ? 'cw-food' : ''}`} aria-label="Timetables">
    <div className="cw-day-tabs" role="group" aria-label="Timetable type"><button aria-pressed={type === 'activities'} onClick={() => { setType('activities'); setDay('') }}><span aria-hidden="true">☀</span>Daily Activities</button><button aria-pressed={type === 'food'} onClick={() => { setType('food'); setDay('') }}><span aria-hidden="true">♧</span>Food Timetable</button></div>
    <details className="cw-day-tools"><summary>Programme options</summary><div className="tt-controls"><CamperSelect label="Timetable" value={type} onChange={value => { setType(value); setDay('') }} options={[{ value:'activities', label:'Daily Activities' },{ value:'food', label:'Food Timetable' }]} /><button type="button" onClick={() => setRevision(value => value + 1)}>Refresh</button><button onClick={() => setDay('')}>Today / next published</button><button onClick={() => window.print()}>Print this day</button></div></details>
    {error && <p role="alert">{error}</p>}{!error && !data && <p role="status">Loading published timetable…</p>}
    {data && <><div className="cw-date-navigator"><button aria-label="Previous day" disabled={!previous} onClick={() => setDay(previous)}>‹</button><CamperSelect label="Camp date" value={data.date} onChange={setDay} options={data.dates.map((row,index) => ({ value: row.date, label: `Day ${index + 1} · ${campDate(row.date)}${row.published ? ' · Published' : ' · Not published'}` }))} /><button aria-label="Next day" disabled={!next} onClick={() => setDay(next)}>›</button></div>
      <div className="cw-day-heading"><div><span className="cp-kicker">{data.date === data.today ? 'YOUR DAY IS HERE' : 'SOMETHING TO LOOK FORWARD TO'}</span><h2>{type === 'food' ? 'At the table' : 'Make today meaningful.'}</h2></div><span className="cw-day-chip">{data.entries.length > 0 ? `Day ${data.entries[0].day_number}` : campDate(data.date)}</span></div><p className="cp-section-note">Today: {data.today} · Africa/Lagos</p>
      {data.state !== 'published' ? <div className="cw-day-empty" role="status"><span aria-hidden="true">✧</span><h3>A little anticipation</h3><p>This day’s timetable has not been published. Please check again later.</p></div> : <ol className="tt-schedule cw-agenda">{data.entries.map((row,index) => <li key={row.id} className={`cw-agenda-item cw-agenda-tone-${index % 3} ${data.current === row.id ? 'tt-current' : ''}`}><div className="cw-agenda-time"><strong>{row.time_label}</strong><span aria-hidden="true">{type === 'food' ? '♧' : '✧'}</span></div><div className="cw-agenda-content">{data.current === row.id && <span className="cw-now">Current activity</span>}{data.upcoming === row.id && <span className="cw-now">Upcoming</span>}<h3>{row.description || 'Meal description not supplied in source.'}</h3>{row.location && <p>{row.location}</p>}{row.instructions && <small>{row.instructions}</small>}{row.certainty === 'proposed' && <small>Proposed</small>}</div></li>)}</ol>}
    </>}
  </section>
}
