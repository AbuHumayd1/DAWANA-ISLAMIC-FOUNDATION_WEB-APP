import CamperSelect from './CamperSelect'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getRegistrationOptions } from '../../services/dicApi'
import { CamperProfile, CamperExplore, CamperArena } from './CamperWorldSections'
import { campDate } from '../../services/dicPresentation'
import { eligibilityLabel } from '../../services/participantIdentity'
import { camperKey, selectedCamper } from '../../services/camperSelection'
import CamperScores from './CamperScores'
import CamperBrand from './CamperBrand'
import CamperTimetables from './CamperTimetables'
import CampUpdates from './CampUpdates'
import CamperHome from './CamperHome'
import { portalDestinations, portalView, activeDestination, digitalIDState } from '../../services/premiumPortal'
import './PremiumCamperPortal.css'
import './CamperWorld.css'

const destinations = portalDestinations
export function PortalIcon({ name }) {
  const paths = { home: 'M3 10 12 3l9 7v11h-6v-7H9v7H3Z', points: 'm12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1Z', houses: 'M4 21V8l8-5 8 5v13M8 21v-7h8v7M8 9h.01M16 9h.01', camp: 'm3 21 9-18 9 18H3Zm6 0 3-6 3 6', profile: 'M20 21v-2a8 8 0 0 0-16 0v2M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z' }
  const extras = { trophy: 'M8 3h8v7a4 4 0 0 1-8 0V3ZM8 5H4v3a4 4 0 0 0 4 4m8-7h4v3a4 4 0 0 1-4 4m-4 2v6m-4 2h8', day: 'M8 2v4m8-4v4M3 10h18M4 4h16v17H4ZM8 14h2m4 0h2m-8 3h2', meals: 'M5 3v7m3-7v7m-6-7v7h6m-3 0v11M19 3c-4 2-4 9 0 9V3Zm0 9v9', id: 'M3 5h18v14H3ZM7 9a2 2 0 1 0 4 0 2 2 0 1 0-4 0Zm-1 7c0-4 6-4 6 0m3-7h3m-3 4h3', feedback: 'M4 3h16v13H9l-5 5V3Zm4 5h8m-8 4h5', explore: 'M12 2a10 10 0 1 0 0 20 10 10 0 1 0 0-20Zm4 6-3 5-5 3 3-5Z' }
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true"><path d={extras[name] || paths[({ arena: 'houses', me: 'profile' })[name] || name] || paths.points} /></svg>
}

export function ContributionList({ rows = [] }) {
  return rows.length ? <ul className="cp-contributions">{rows.map(row => <li key={row.id}><span className="cp-activity-icon"><PortalIcon name="points" /></span><div><strong>{row.activity}</strong><small>{campDate(row.date)}{row.slot && ` · ${row.slot.replaceAll('_', ' ')}`}<br />{row.house}</small></div><b>{row.reversed ? <><s>+{row.points}</s><small>Reversed · 0</small></> : `+${row.points}`}</b></li>)}</ul> : <div className="cp-empty"><PortalIcon name="points" /><strong>Your contributions start here</strong><p>Verified achievements will appear after an authorised officer records them.</p></div>
}

export function HouseArena({ data, house, compact = false }) {
  if (!data?.standings_ready) return <div className="cp-empty"><strong>Standings are being prepared</strong><p>House totals will appear when scoring storage is available.</p></div>
  const rows = compact ? data.standings.slice(0, 3) : data.standings
  return rows.length ? <ol className={`cp-arena cw-leaderboard ${compact ? 'cw-leaderboard-compact' : ''}`} aria-label="Overall house standings">{rows.map((row, index) => <li key={row.house_id} className={`cw-place-${row.rank <= 3 ? row.rank : 'other'} ${row.name === house ? 'cp-own-house' : ''}`}><span className="cw-medal" aria-label={`Position ${row.rank}`}><span className="cp-rank">{row.rank}</span></span><span className={`cw-house-emblem cw-house-tone-${index % 4}`} aria-hidden="true"><PortalIcon name="arena" /></span><div><strong>{row.name}</strong><small>{row.name === house ? 'Your house · ' : ''}{row.gender || 'Participant house'}</small></div><b>{row.net}<small>points</small></b></li>)}</ol> : <div className="cp-empty"><strong>The championship awaits</strong><p>No participant houses are configured for this edition yet.</p></div>
}

export function DigitalIDStatus({ participant, onOpenID, busy }) {
  const state = digitalIDState(participant)
  return <section className="cp-card cp-id-entry"><span className="cp-id-emblem"><PortalIcon name="id" /></span><span className="cp-kicker">YOUR CAMP IDENTITY</span><h2>{state.title}</h2><p>{state.detail}</p><p>{eligibilityLabel(participant.eligibility.code)}</p><p>ID: {participant.issue?.status || 'Not issued'}</p>{state.available ? <button className="button" disabled={busy} onClick={() => onOpenID(participant)}>Open my Digital ID</button> : <p className="cp-pending-label" role="status">Awaiting active ID</p>}</section>
}

export function ExperienceContent({ tab, participant: p, order, data, error, onNavigate, onPage, onRefresh, onOpenID, busy, camp, timetableType }) {
  const tutor = p.registration_basis === 'tutor'
  const resolvedView = portalView(tab)
  const view = tutor && resolvedView === 'arena' ? 'me' : resolvedView
  const scoreState = error ? <div className="participant-error" role="alert"><p>{error}</p><button className="cp-text-button" onClick={onRefresh}>Retry points</button></div> : !data ? <p className="cp-skeleton" role="status">Loading verified camp points…</p> : !data.ready ? <p className="participant-notice" role="status">{data.message}</p> : null
  if (view === 'day') return <><div className="cp-section-heading"><span className="cp-kicker">A DAY FULL OF POSSIBILITY</span><h1>My Day</h1><p>Published activities, shared meals and moments that matter.</p></div><CamperTimetables key={`${p.registration_item_id}:${timetableType}`} item={p.registration_item_id} initialType={timetableType} /></>
  if (view === 'digital-id') return <><div className="cp-section-heading"><h1>My Digital ID</h1></div><DigitalIDStatus participant={p} onOpenID={onOpenID} busy={busy} /><button className="cp-text-button" onClick={() => onNavigate('me')}>Back to my profile</button></>
  if (view === 'me') return <CamperProfile participant={p} order={order} ID={DigitalIDStatus} Icon={PortalIcon} onOpenID={onOpenID} busy={busy} />
  if (view === 'feedback') return <><div className="cp-section-heading"><span className="cp-kicker">WE ARE LISTENING</span><h1>Your voice matters</h1><p>Use your verified booking to share your experience.</p></div><div className="cp-explore-grid">{[['daily', 'Daily feedback', 'Reflect on your camp day.'], ['welfare', 'Submit a complaint', 'Raise a welfare concern securely.'], ['history', 'My complaints / complaint status', 'Follow updates on your existing concerns.'], ['final', 'Final camp evaluation', 'Help shape the next camp experience.']].map(([channel, title, text]) => <Link className="cp-card cp-link-card" key={channel} to={`/dic/feedback?channel=${channel}`}><div><h2>{title}</h2><p>{text}</p></div><span aria-hidden="true">↗</span></Link>)}</div></>
  if (view === 'announcements') return <><div className="cp-section-heading"><span className="cp-kicker">IN THE KNOW</span><h1>Camp announcements</h1></div><CampUpdates key={p.registration_item_id} item={p.registration_item_id} /></>
  if (view === 'explore') return <CamperExplore participant={p} camp={camp} onNavigate={onNavigate} Icon={PortalIcon} />
  if (view === 'arena') return <CamperArena participant={p} data={data} scoreState={scoreState} onRefresh={onRefresh} onPage={onPage} Arena={HouseArena} Contributions={ContributionList} Icon={PortalIcon} />
  return <CamperHome key={p.registration_item_id} participant={p} data={data} scoreState={!tutor && scoreState} onNavigate={onNavigate} Icon={PortalIcon} Arena={HouseArena} />
}

export default function CamperExperience({ orders, selection, onSelect, busy, onOpenID, onLogout, onRefreshBookings, loggingOut, expiresAt, accountSettings }) {
  const [params, setParams] = useSearchParams()
  const selected = selectedCamper(orders, selection)
  const requestedTab = portalView(params.get('view'))
  const tab = selected?.participant.registration_basis === 'tutor' && requestedTab === 'arena' ? 'me' : requestedTab
  const timetableType = params.get('type') === 'food' ? 'food' : 'activities'
  const [camp, setCamp] = useState(null)
  const contentRef = useRef(null)
  const previousView = useRef(null)
  useEffect(() => {
    const controller = new AbortController()
    getRegistrationOptions({ signal: controller.signal }).then(data => { if (!controller.signal.aborted) setCamp(data) }).catch(() => {})
    return () => controller.abort()
  }, [])
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
    if (previousView.current !== null) contentRef.current?.focus({ preventScroll: true })
    previousView.current = tab
  }, [tab, selected?.key])
  const navigate = (view, type) => setParams(view === 'home' ? {} : { view, ...(type === 'food' ? { type } : {}) })
  if (!selected) return <div className="cp-card"><h1>No authorised campers</h1><p>Verify the booking that contains your camper.</p><button onClick={onLogout}>Secure logout</button></div>
  const { participant, order } = selected
  const tutor = participant.registration_basis === 'tutor'
  const navigation = destinations.filter(([key]) => !tutor || key !== 'arena')
  const colour = participant.house_assignment?.colour
  const content = state => <div className="cp-page" key={tab}><ExperienceContent {...state} tab={tab} participant={participant} order={order} onNavigate={(view, type) => { state.onPage?.(1); navigate(view, type) }} onOpenID={onOpenID} busy={busy} camp={camp?.name === order.edition ? camp : null} timetableType={timetableType} /></div>
  return <div className="cp-experience" style={/^#[0-9a-f]{6}$/i.test(colour || '') ? { '--cp-house': colour } : undefined}>
    <a className="cp-skip-link" href="#cp-view">Skip to camper content</a><header className="cp-header"><Link to="/dic" className="cp-brand"><CamperBrand /></Link><div className="cw-header-switch"><CamperSelect label="My camper" value={selected.key} disabled={busy} onChange={onSelect} options={orders.flatMap(booking => booking.participants.map(person => ({ value: camperKey(booking, person), label: person.name })))} /></div><button className="cp-profile-shortcut" aria-label="Open my profile" onClick={() => navigate('me')}>{participant.name?.slice(0, 1)}</button></header>
    <nav className="cp-navigation" aria-label="Camper navigation" style={{ gridTemplateColumns: `repeat(${navigation.length}, minmax(0, 1fr))` }}>{navigation.map(([key, label]) => <button key={key} aria-current={activeDestination(tab) === key ? 'page' : undefined} onClick={() => navigate(key)}><PortalIcon name={key} /><span>{label}</span></button>)}</nav>
    <div className="cp-main">
      <div id="cp-view" ref={contentRef} tabIndex={-1} className="cp-view" aria-label={`${activeDestination(tab)} content`}>{tutor ? content({}) : <CamperScores key={selected.key} item={participant.registration_item_id} destination={tab}>{content}</CamperScores>}</div>
      {tab === 'me' && <details className="cw-account-drawer"><summary><PortalIcon name="profile" /><span>Account & security<small>Sign-in settings, registration refresh & secure logout</small></span><span aria-hidden="true">+</span></summary><div className="cp-security-settings">{accountSettings}</div><section className="cp-session-controls"><h2>Secure booking access</h2><p>Session expires {new Date(expiresAt).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}. This session covers your verified booking.</p><button disabled={busy} onClick={onRefreshBookings}>Refresh registrations</button><button disabled={loggingOut} onClick={onLogout}>Secure logout</button></section></details>}
      <footer className="cp-footer">A journey of faith, friendship & meaningful contribution.<br /><Link to="/dic">Back to DIC</Link></footer>
    </div>
  </div>
}
