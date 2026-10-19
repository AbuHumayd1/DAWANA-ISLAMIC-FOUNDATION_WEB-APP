import { useEffect, useState } from 'react'
import { getOperationsData, postOperationsData } from '../services/operationsApi'
import { ParticipantIDCard } from './ParticipantPortal'
import { createLatestResource } from '../services/requestScope'
import { eligibilityLabel } from '../services/participantIdentity'

export default function StaffParticipantIDs({ user }) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState('')
  const [page, setPage] = useState(1)
  const [listing, setListing] = useState({ data: null, loading: true, error: '' })
  const { data } = listing
  const [revision, setRevision] = useState(0)
  const [resource] = useState(() => createLatestResource(
    ({ query, page }, signal) => getOperationsData(`/enrollments/?q=${encodeURIComponent(query)}&page=${page}`, { signal }), setListing))
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [card, setCard] = useState(null)
  const [reason, setReason] = useState('')
  const [source, setSource] = useState({})
  const [restrictions, setRestrictions] = useState({})
  const load = () => resource.run({ query: active, page })
  useEffect(() => {
    resource.run({ query: active, page })
    return () => resource.cancel()
  }, [resource, active, page, revision])
  const perform = async (action) => {
    setLoading(true); setError('')
    try { await action(); await load() } catch (e) { setError(e.message) } finally { setLoading(false) }
  }
  const manage = (enrollment, action) => perform(() => postOperationsData(`/enrollments/${enrollment.id}/id/`, { action, reason, ...(action === 'review_source' ? { source_item_id: Number(source[enrollment.id]), restriction_reason: restrictions[enrollment.id] ?? enrollment.restriction_reason ?? '' } : {}) }))
  if (card) return <ParticipantIDCard card={card} onClose={() => setCard(null)} />
  return <>
    <div className="ops-page-heading"><div><span className="ops-eyebrow">Individual identification</span><h1>Participant IDs</h1><p>Live eligibility and issue status. Identification does not authorize camp entry or departure.</p></div></div>
    {(error || listing.error) && <p className="participant-error" role="alert">{error || listing.error}</p>}
    <div className="staff-id-controls"><form className="ops-filterbar" onSubmit={(e) => { e.preventDefault(); if (loading) return; setPage(1); setActive(query); setError(''); setRevision((value) => value + 1) }}><label className="ops-filter">Participant number, booking reference or name<input disabled={loading} value={query} onChange={(e) => setQuery(e.target.value)} /></label><button className="ops-button ops-button-primary" disabled={loading}>Search</button></form>
      {(user.permissions.manage_ids || user.permissions.review_id_sources) && <label className="ops-filter">Reason for sensitive changes<input maxLength={240} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Required for replacement, revocation and source review" /></label>}
    </div>
    {listing.loading && <button className="ops-button ops-button-secondary" onClick={() => resource.cancel(true)}>Cancel search</button>}
    {listing.error && <button className="ops-button ops-button-secondary" onClick={() => setRevision((value) => value + 1)}>Retry search</button>}
    {!data ? <p role="status">{listing.loading ? 'Loading participant identification...' : listing.cancelled ? 'Search cancelled.' : 'No search results loaded.'}</p> : <>
      <div className="participant-grid">{data.results.map((enrollment) => <article className="participant-summary" key={enrollment.id}><h2>{enrollment.name}</h2><p>{enrollment.participant_number}</p><p>{eligibilityLabel(enrollment.eligibility.code)}</p><p>ID: {enrollment.issue?.status || 'not issued'} {enrollment.issue && `· version ${enrollment.issue.version}`}</p><div className="portal-id-actions">
        <button className="ops-button ops-button-secondary" disabled={loading || !enrollment.eligibility.eligible || enrollment.issue?.status !== 'current'} onClick={() => perform(async () => setCard(await getOperationsData(`/enrollments/${enrollment.id}/id/`)))}>View / print current ID</button>
        {user.permissions.manage_ids && <><button className="ops-button ops-button-primary" disabled={loading || !enrollment.eligibility.eligible} onClick={() => manage(enrollment, enrollment.issue ? 'reissue' : 'issue')}>{enrollment.issue ? 'Replace ID' : 'Issue ID'}</button><button className="ops-button ops-button-secondary" disabled={loading || enrollment.issue?.status !== 'current'} onClick={() => manage(enrollment, 'revoke')}>Revoke ID</button></>}
      </div>{user.permissions.review_id_sources && <div className="staff-id-controls"><label className="ops-filter">Reviewed registration source<select value={source[enrollment.id] || ''} onChange={(e) => setSource({ ...source, [enrollment.id]: e.target.value })}><option value="">Select source after reviewing evidence</option>{enrollment.sources.map((item) => <option key={item.id} value={item.id}>{item.reference} · {item.status} / {item.payment_status}</option>)}</select></label><label className="ops-filter">ID eligibility restriction (blank clears after review)<input maxLength={240} value={restrictions[enrollment.id] ?? enrollment.restriction_reason} onChange={(e) => setRestrictions({ ...restrictions, [enrollment.id]: e.target.value })} /></label><p>Saving a source review revokes any current issue. It does not change payment evidence.</p><button className="ops-button ops-button-secondary" disabled={loading || !source[enrollment.id]} onClick={() => manage(enrollment, 'review_source')}>Save reviewed source / restriction</button></div>}</article>)}</div>
      {data.results.length === 0 && <p>No enrollments match. Search the registration candidates below to prepare an enrollment.</p>}
      {data.pages > 1 && <div className="ops-pagination"><button disabled={loading || page <= 1} onClick={() => { setError(''); setPage(page - 1) }}>Previous</button><span>Page {data.page} of {data.pages}</span><button disabled={loading || page >= data.pages} onClick={() => { setError(''); setPage(page + 1) }}>Next</button></div>}
      {user.permissions.manage_ids && <section className="ops-panel staff-id-controls"><h2>Registration candidates</h2><p>Up to 25 matching participants. Preparing an enrollment creates an individual number; it does not verify payment or issue an ID.</p>{data.registration_candidates.map((item) => <div className="ops-detail-row" key={item.registration_item_id}><span>{item.name} · {item.edition} · {item.category}</span><button className="ops-button ops-button-secondary" disabled={loading} onClick={() => perform(() => postOperationsData('/enrollments/', { registration_item_id: item.registration_item_id }))}>Prepare enrollment</button></div>)}</section>}
    </>}
  </>
}
