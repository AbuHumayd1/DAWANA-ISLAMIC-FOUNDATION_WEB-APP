import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getOperationsData, postOperationsData, getCheckInPrintUrl } from '../services/operationsApi'
import { checkInPath, checkInTime } from '../services/checkIn'
import CamperScanner from '../components/operations/CamperScanner'

export function CheckInResults({ rows, canCheckIn, busy, onCheckIn, canViewMovements = false, onMovement }) {
  return <div className="checkin-list">{rows.map(row => <article className="ops-panel checkin-person" key={row.participant_id}>
    <div><h2>{row.name}</h2><p className="checkin-number">Registration: {row.registration_number}</p>
      {row.participant_number !== row.registration_number && <p className="checkin-number">Participant ID: {row.participant_number}</p>}
      <dl><div><dt>Registration</dt><dd>{row.registration_status}</dd></div>
        <div><dt>Payment</dt><dd>{row.payment_status}</dd></div>
        <div><dt>Check-in eligibility</dt><dd>{row.eligibility.label}</dd></div>
        <div><dt>House</dt><dd>{row.house || 'Pending assignment'}</dd></div></dl></div>
    <div className="checkin-arrival">{row.check_in ? <><strong>Checked In (initial arrival only)</strong><span>{checkInTime(row.check_in.time)}</span><span>By {row.check_in.staff}</span></>
      : <><strong>Not yet arrived</strong>{canCheckIn ? <button type="button" className="ops-button ops-button-primary"
        disabled={!row.eligibility.eligible || Boolean(busy)} onClick={() => onCheckIn(row)}>{busy === row.participant_id ? 'Checking in…' : 'Check In'}</button>
        : <span>Check-in permission required</span>}
        {!row.eligibility.eligible && <span>Resolve the eligibility issue before check-in.</span>}</>}</div>
    {canViewMovements && <button type="button" className="ops-button ops-button-secondary" disabled={Boolean(busy)} onClick={() => onMovement(row)}>Movement history / record</button>}
  </article>)}</div>
}

export default function CampCheckIn({ user }) {
  const [params, setParams] = useSearchParams()
  const edition = params.get('edition') || ''
  const search = params.get('search') || ''
  const page = Number(params.get('page') || 1)
  const [draftState, setDraft] = useState({ search, value: search })
  const draft = draftState.search === search ? draftState.value : search
  const [state, setState] = useState({ path: '', data: null, error: '' })
  const [refresh, setRefresh] = useState(0)
  const [busy, setBusy] = useState('')
  const [scanner, setScanner] = useState(null)
  const [notice, setNotice] = useState({ path: '', message: '' })
  const submitting = useRef(false)
  const currentPath = useRef('')
  let path, pathError
  try { path = checkInPath(edition, search, page) } catch (error) { pathError = error.message }
  useEffect(() => {
    currentPath.current = path
    return () => { currentPath.current = '' }
  }, [path])
  useEffect(() => {
    if (!path) return
    let live = true
    const controller = new AbortController()
    getOperationsData(path, { signal: controller.signal }).then(data => {
      if (live) setState({ path, data, error: '' })
    }).catch(error => { if (live) setState({ path, data: null, error: error.message }) })
    return () => { live = false; controller.abort() }
  }, [path, refresh])
  const error = pathError || (state.path === path ? state.error : '')
  const data = !error && state.path === path ? state.data : null
  const reload = () => { setState({ path: '', data: null, error: '' }); setRefresh(value => value + 1) }
  const query = (nextEdition, nextSearch, nextPage = 1) => {
    setScanner(null)
    setParams({ ...(nextEdition ? { edition: String(nextEdition) } : {}), ...(nextSearch ? { search: nextSearch } : {}), page: String(nextPage) })
  }
  async function arrive(row) {
    if (submitting.current || !data?.edition || !row.eligibility.eligible || !user.permissions.check_in) return
    if (!window.confirm(`Record initial camp arrival for ${row.name}?`)) return
    submitting.current = true
    const submittedPath = path
    setBusy(row.participant_id); setNotice({ path: '', message: '' })
    try {
      const result = await postOperationsData(checkInPath(data.edition.id), { participant_id: row.participant_id })
      if (currentPath.current === submittedPath) {
        setNotice({ path: submittedPath, message: result.created ? `${row.name} checked in.` : `${row.name} was already checked in. The original record is unchanged.` })
        reload()
      }
    } catch (failure) {
      if (currentPath.current === submittedPath) { setNotice({ path: submittedPath, message: failure.message }); reload() }
    } finally { submitting.current = false; setBusy('') }
  }
  return <>
    <div className="ops-page-heading"><div><span className="ops-eyebrow">Physical arrival at camp</span><h1>Camp Check-in</h1><p>Find a participant and record their arrival. This is separate from daily attendance.</p></div></div>
    <p role="status" aria-live="polite">{notice.path === path ? notice.message : ''}</p>
    {error ? <section className="ops-error" role="alert"><p>{error}</p><button className="ops-button" onClick={reload}>Retry</button><button className="ops-button" onClick={() => setParams({})}>Use current edition</button></section>
      : !data ? <p role="status" aria-busy="true">Loading check-in list…</p> : <>
        <form className="ops-panel checkin-controls" onSubmit={event => { event.preventDefault(); query(data.edition?.id, draft.trim()) }}>
          <label>Camp edition<select value={data.edition?.id || ''} disabled={Boolean(busy)} onChange={event => query(event.target.value, search)}>
            {!data.edition && <option value="">No camp edition configured</option>}{data.editions.map(item => <option value={item.id} key={item.id}>{item.name} ({item.year})</option>)}
          </select></label>
          <label>Participant name or registration number<input type="search" value={draft} maxLength={200} onChange={event => setDraft({ search, value: event.target.value })} /></label>
          <button className="ops-button ops-button-primary" disabled={Boolean(busy)}>Search</button>
          <button type="button" className="ops-button ops-button-secondary" onClick={() => query(data.edition?.id, '')}>Clear</button>
          <button type="button" className="ops-button ops-button-secondary" disabled={Boolean(busy)} onClick={reload}>Refresh</button>
          {data.edition && user.permissions.ids && (user.permissions.check_in || user.permissions.movement_view) && <button type="button" className="ops-button ops-button-primary" disabled={Boolean(busy)} onClick={() => setScanner({ edition: data.edition.id, participant: null })}>Scan ID</button>}
          {data.edition && user.permissions.export_reports && <a className="ops-button ops-button-secondary" target="_blank" rel="noopener noreferrer" href={getCheckInPrintUrl(data.edition.id, search)}>Print list</a>}
        </form>
        {scanner && scanner.edition === data.edition?.id && <CamperScanner key={`${scanner.edition}:${scanner.participant?.participant_id || 'scan'}`} edition={scanner.edition} user={user} participant={scanner.participant} onClose={() => setScanner(null)} onSaved={message => { setScanner(null); setNotice({ path, message }); reload() }} />}
        {data.edition && <p className="campsite-context">Showing <strong>{data.edition.name}</strong>. Totals cover the whole edition; Needs Attention includes all participants who are not currently eligible.</p>}
        {data.totals && <section className="ops-metric-grid" aria-label="Check-in totals">{[['registered','Registered'],['checked_in','Checked In'],['not_yet_arrived','Not Yet Arrived'],['needs_attention','Needs Attention']].map(([key,label]) => <article className="ops-metric-card" key={key}><div className="ops-metric-copy"><span>{label}</span><strong>{data.totals[key]}</strong></div></article>)}</section>}
        {!user.permissions.check_in && <p className="ops-small-note">You can view arrivals. An administrator must explicitly grant Camp Check-in permission before you can check participants in.</p>}
        <CheckInResults rows={data.results} canCheckIn={user.permissions.check_in} busy={busy} onCheckIn={arrive} canViewMovements={user.permissions.movement_view} onMovement={row => setScanner({ edition: data.edition.id, participant: row })} />
        {!data.results.length && <section className="ops-panel"><p>{data.edition ? 'No participants match this search.' : 'No camp edition configured.'}</p></section>}
        {data.count > 0 && <div className="checkin-pagination"><button className="ops-button ops-button-secondary" disabled={page <= 1 || Boolean(busy)} onClick={() => query(data.edition.id, search, page-1)}>Previous</button><span>Page {page} of {Math.ceil(data.count / data.page_size)} · {data.count} participants</span><button className="ops-button ops-button-secondary" disabled={page * data.page_size >= data.count || Boolean(busy)} onClick={() => query(data.edition.id, search, page+1)}>Next</button></div>}
        <p className="ops-small-note">The print list includes all search results, across every page. Printed lists require existing report export permission. Housing pending does not prevent an otherwise eligible arrival.</p>
      </>}
  </>
}
