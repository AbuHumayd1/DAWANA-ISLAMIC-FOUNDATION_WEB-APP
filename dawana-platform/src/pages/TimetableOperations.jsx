import { useEffect, useState } from 'react'
import { getOperationsData } from '../services/operationsApi'
import { backendUrl } from '../services/productionContract'

export default function TimetableOperations() {
  const [edition, setEdition] = useState(''), [state, setState] = useState({ path: '', data: null, error: '' })
  const path = '/timetables/' + (edition ? '?edition=' + encodeURIComponent(edition) : '')
  useEffect(() => {
    const controller = new AbortController()
    getOperationsData(path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ path, data, error: '' })
    }).catch(error => { if (!controller.signal.aborted) setState({ path, data: null, error: error.message }) })
    return () => controller.abort()
  }, [path])
  const data = state.path === path ? state.data : null, error = state.path === path ? state.error : ''
  return <section className="ops-panel"><h1>Timetables</h1><p>Daily Activities and Food Timetable. Edit drafts, preview days, and deliberately publish in Django Admin.</p>
    {error && <p role="alert">{error}</p>}{!data && !error && <p>Loading timetable status…</p>}
    {data && <><label>Camp edition <select value={edition} onChange={event => setEdition(event.target.value)}><option value="">Choose edition</option>{data.editions.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      <p>{data.can_edit ? 'Draft editing permitted.' : 'Draft editing not permitted.'} {data.can_publish ? 'Publication permitted.' : 'Publication not permitted.'}</p>
      <a className="button" href={backendUrl(data.admin_url) + (edition ? '?edition__id__exact=' + encodeURIComponent(edition) : '')}>Open Django Admin timetables</a>
      {data.setup_pending ? <p>Timetable schema setup is pending approval.</p> : edition && !data.days.length ? <p>No timetable entries for this edition.</p> : <ul>{data.days.map(row => <li key={[row.date, row.timetable_type, row.status].join(':')}>{row.date} · {row.timetable_type === 'food' ? 'Food Timetable' : 'Daily Activities'} · {row.status} · {row.entries} entries</li>)}</ul>}
    </>}
  </section>
}
