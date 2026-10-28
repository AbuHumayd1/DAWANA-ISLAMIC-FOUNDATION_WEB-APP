import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getOperationsData } from '../services/operationsApi'
import { campsiteModules, campsiteMetricValue, campsiteOverviewPath } from '../services/campsiteModules'
import { HelpDetails } from '../components/operations/OperationsControls'

export function PlannedCampsiteModule({ moduleKey, user }) {
  const module = campsiteModules[moduleKey]
  if (!module || (module.permission && !user.permissions[module.permission])) {
    return <section className="ops-panel" role="alert"><h1>Access denied</h1><p>Your account does not have permission to view this module.</p></section>
  }
  if (module.implemented) return <section className="ops-panel"><h1>{module.title}</h1><p>{module.available}</p><Link to={`/dic/operations/${moduleKey}`}>Open {module.title}</Link></section>
  return <>
    <div className="ops-page-heading"><div><span className="ops-eyebrow">Campsite operations · Planned module</span><h1>{module.title}</h1><p>{module.summary}</p></div></div>
    <section className="ops-panel"><h2>Coming in a later phase</h2><p>{module.available}</p>
      <HelpDetails label="What is planned?"><p>{module.approvals}</p><ul className="campsite-plan-list">{module.planned.map(item => <li key={item}>{item}</li>)}</ul>
      <p>Records and reports will be kept separately for each camp. New forms and approvals will be added in later phases.</p></HelpDetails>
      {moduleKey === 'finance' && <Link className="ops-button ops-button-secondary" to="/dic/operations/payments">Review registration payment attempts</Link>}
      {moduleKey === 'reporting-hub' && user.permissions.export_reports && <Link className="ops-button ops-button-secondary" to="/dic/operations/reports">Open existing operational exports</Link>}
    </section>
  </>
}

const metricDefinitions = [
  ['registered_participants', 'Registered participants', 'All registration records'],
  ['eligible_participants', 'Verified eligible participants', 'Payment and ID checks passed'],
  ['awaiting_payment_verification', 'Awaiting verification', 'Registration or payment pending'],
  ['assigned_participants', 'Assigned to houses', 'Recorded house assignments'],
  ['awaiting_house_assignment', 'Awaiting a house', 'Eligible, without an assignment'],
  ['active_ids', 'Active participant ID cards', 'Eligible, issued and unexpired'],
  ['requiring_attention', 'Needs attention', 'Staff review required'],
  ['attendance', 'Campsite attendance', 'Not yet available'],
]

export function CampsiteMetrics({ metrics, definitions }) {
  return <><section className="ops-metric-grid campsite-metrics" aria-label="Campsite readiness metrics">
    {metricDefinitions.map(([key,label,note]) => <article className="ops-metric-card" key={key} title={definitions?.[key]}>
      <div className="ops-metric-copy"><span>{label}</span><strong>{campsiteMetricValue(metrics?.[key])}</strong><small>{note}</small></div>
    </article>)}
  </section><HelpDetails><p>ID cards and house assignments do not confirm that someone has arrived at camp.</p>
    <dl className="ops-metric-definitions">{metricDefinitions.map(([key,label]) => <div key={key}><dt>{label}</dt><dd>{definitions?.[key] || 'Definition unavailable; refresh the overview.'}</dd></div>)}</dl>
  </HelpDetails></>
}

export default function CampsiteFoundation({ user }) {
  const [params, setParams] = useSearchParams()
  const edition = params.get('edition') || ''
  const [state, setState] = useState({ data: null, error: '', path: '' })
  const [refresh, setRefresh] = useState(0)
  let path, pathError
  try { path = campsiteOverviewPath(edition) } catch (error) { pathError = error.message }
  useEffect(() => {
    if (!path) return
    let live = true
    const controller = new AbortController()
    getOperationsData(path, { signal: controller.signal })
      .then(data => { if (live) setState({ data, path, error: '' }) })
      .catch(error => { if (live) setState({ data: null, path, error: error.message }) })
    return () => { live = false; controller.abort() }
  }, [path, refresh])
  const loading = path && state.path !== path
  const error = pathError || (state.path === path && state.error)
  const data = !loading && !error ? state.data : null
  return <>
    <div className="ops-page-heading"><div><span className="ops-eyebrow">DIC staff workspace</span><h1>Campsite operations</h1><p>Your camp information at a glance.</p></div></div>
    {error ? <section className="ops-error" role="alert"><p>{error}</p><button className="ops-button ops-button-secondary" onClick={() => { setState({ data: null, error: '', path: '' }); setRefresh(value => value+1) }}>Retry overview</button>{edition && <button className="ops-button ops-button-secondary" onClick={() => setParams({})}>Use current edition</button>}</section>
      : loading || !data ? <section className="ops-panel" aria-busy="true" role="status">Loading authorised campsite information…</section>
        : <>
          <label className="ops-filter campsite-edition">Camp edition<select value={data.edition?.id || ''} onChange={event => setParams({ edition: event.target.value })}>
            {!data.edition && <option value="">No camp edition configured</option>}
            {(data.editions || []).map(item => <option key={item.id} value={item.id}>{item.name} ({item.year})</option>)}
          </select></label>
          {!data.edition ? <section className="ops-panel"><h2>No camp edition configured</h2><p>An authorised administrator must configure the camp before operational metrics are available.</p></section>
            : <><p className="campsite-context">Showing <strong>{data.edition.name}</strong>.</p>
              <CampsiteMetrics metrics={data.metrics} definitions={data.definitions} />
              <p className="ops-small-note">Other pages have their own camp filters or default camp selection.</p></>}
        </>}
    <section className="ops-panel"><h2>Quick links</h2><div className="campsite-module-grid">
        {user.permissions.export_reports && <Link to="/dic/operations/reporting-hub"><strong>Comprehensive reporting</strong><span>Permission-scoped analytics, CSV and printable reports.</span></Link>}
      <Link to="/dic/operations/check-in"><strong>Camp Check-in</strong><span>Find participants and record physical arrival.</span></Link>
      {user.permissions.scores && <Link to="/dic/operations/scoring"><strong>House scoring</strong><span>Combined leaderboard and scoring history.</span></Link>}
      <Link to="/dic/operations/participants"><strong>Participants</strong><span>Find registrations and participant details.</span></Link>
      <Link to="/dic/operations/houses"><strong>House allocation</strong><span>See house assignments.</span></Link>
      {user.permissions.ids && <Link to="/dic/operations/participant-ids"><strong>Participant IDs</strong><span>Check ID status and view cards.</span></Link>}
      {user.permissions.manage_ids && <Link to="/dic/operations/id-printing"><strong>ID Card Printing</strong><span>Download cards and review print history.</span></Link>}
    </div></section>
      {Object.values(campsiteModules).some(module=>!module.implemented&&(!module.permission||user.permissions[module.permission]))&&<details className="ops-panel ops-upcoming"><summary>Planned camp tools</summary><p>These tools are planned and are not yet available.</p><div className="campsite-module-grid">
        {Object.entries(campsiteModules).filter(([, module]) => !module.implemented&&(!module.permission || user.permissions[module.permission])).map(([key,module]) => <Link to={`/dic/operations/${key}`} key={key}><strong>{module.title}</strong><span>{module.summary}</span><small>Planned</small></Link>)}
      </div></details>}
  </>
}
