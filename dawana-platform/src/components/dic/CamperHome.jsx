import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { timetablePath } from '../../services/timetables'
import { campDayLabel, todayProgramme } from '../../services/premiumPortal'
import { campDate } from '../../services/dicPresentation'
import CampUpdates from './CampUpdates'

function usePublishedActivities(item) {
  const [state, setState] = useState(null), [revision, setRevision] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setRevision(value => value + 1), 60000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    participantRequest(timetablePath(item, 'activities'), undefined, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ item, revision, data }) })
      .catch(error => { if (!controller.signal.aborted) setState({ item, revision, error: error.message }) })
    return () => controller.abort()
  }, [item, revision])
  return { data: state?.item === item && state?.revision === revision ? state.data : null,
    error: state?.item === item && state?.revision === revision ? state.error : '',
    retry: () => setRevision(value => value + 1) }
}

export function ProgrammePreview({ data, error, onNavigate, onRetry }) {
  const entries = todayProgramme(data)
  const upcomingIndex = entries.findIndex(row => row.id === data?.current || row.id === data?.upcoming)
  const preview = entries.slice(Math.max(0, upcomingIndex), Math.max(0, upcomingIndex) + 2)
  return <section className="cp-card cp-programme"><div className="cp-card-title"><div><span className="cp-kicker">MAKE TODAY MEANINGFUL</span><h2>Today’s programme</h2></div><button onClick={() => onNavigate('day')}>Full day <span aria-hidden="true">↗</span></button></div>
    {error ? <div role="alert"><p>{error}</p><button className="cp-text-button" onClick={onRetry}>Retry programme</button></div>
      : !data ? <p role="status">Loading published activities…</p>
        : entries.length ? <><p className="cp-date-label">{campDate(data.today)} · {data.timezone}</p><ol className="cp-programme-list">{preview.map(row => <li key={row.id}><div className="cp-programme-time">{row.time_label}{data.current === row.id && <small>Happening now</small>}{data.upcoming === row.id && <small>Up next</small>}</div><div><h3>{row.description || 'Activity details pending'}</h3>{row.location && <p>{row.location}</p>}{row.instructions && <p>{row.instructions}</p>}{row.certainty === 'proposed' && <small>Proposed</small>}</div><span className="cw-activity-star" aria-hidden="true">✧</span></li>)}</ol></>
          : <div className="cp-empty"><span className="cp-empty-symbol" aria-hidden="true">☀</span><strong>A little anticipation, a wonderful journey</strong><p>No activities are published for today. Explore the full programme for approved camp dates.</p><button className="cp-text-button" onClick={() => onNavigate('day')}>Explore the programme →</button></div>}
  </section>
}

const tiles = [
  { label: 'Activities', detail: 'Your day, beautifully planned', icon: 'day', view: 'day', tone: 'mint' },
  { label: 'Meals', detail: 'Something good is coming', icon: 'meals', view: 'day', type: 'food', tone: 'amber' },
  { label: 'House Arena', detail: 'Together, every point matters', icon: 'arena', view: 'arena', tone: 'lavender' },
  { label: 'My Digital ID', detail: 'Your identity. Your camp.', icon: 'id', view: 'digital-id', tone: 'sky' },
  { label: 'Discover', detail: 'Learn, connect & explore', icon: 'explore', view: 'explore', tone: 'coral' },
  { label: 'Feedback', detail: 'Your voice belongs here', icon: 'feedback', view: 'feedback', tone: 'yellow' },
]

export function FeatureTiles({ onNavigate, Icon, tutor }) {
  return <section className="cp-shortcuts" aria-labelledby="cp-shortcuts-title"><div className="cp-section-heading"><span className="cp-kicker">YOUR CAMP, CONNECTED</span><h2 id="cp-shortcuts-title">Everything, one tap away.</h2></div><div className="cp-tile-grid">{tiles.filter(tile => !tutor || tile.view !== 'arena').map(tile => <button key={tile.label} className={`cp-feature-tile cp-tone-${tile.tone}`} onClick={() => onNavigate(tile.view, tile.type)}><span className="cp-tile-icon"><Icon name={tile.icon} /></span><span className="cp-tile-arrow" aria-hidden="true">↗</span><strong>{tile.label}</strong><span>{tile.detail}</span></button>)}</div></section>
}

export default function CamperHome({ participant, data, scoreState, onNavigate, Icon, Arena }) {
  const published = usePublishedActivities(participant.registration_item_id)
  const house = participant.house_assignment?.name
  const tutor = participant.registration_basis === 'tutor'
  return <>
    <section className="cp-welcome"><div className="cw-hero-copy"><span className="cp-kicker">DIC CAMPER WORLD</span><h1>As-salāmu ʿalaykum,<br /><span>{participant.name}.</span></h1><p>Welcome to your DIC experience.</p></div><div className="cw-hero-art" aria-hidden="true"><span>✦</span><Icon name="camp" /><span>☾</span></div><div className="cp-hero-status"><span><Icon name="day" /><small>Your journey</small><strong>{campDayLabel(published.data)}</strong></span>{!tutor && <span><Icon name="points" /><small>Verified points</small><strong>{data?.ready ? data.total : 'Not yet available'}</strong></span>}<span><Icon name={tutor ? 'explore' : 'arena'} /><small>{tutor ? 'Your role' : 'Your house'}</small><strong>{tutor ? 'Camp tutor' : house || 'Assignment coming soon'}</strong></span></div></section>
    <FeatureTiles onNavigate={onNavigate} Icon={Icon} tutor={tutor} />
    <div className="cp-home-columns"><ProgrammePreview {...published} onRetry={published.retry} onNavigate={onNavigate} />{!tutor && <section className="cp-card cp-championship"><div className="cp-card-title"><div><span className="cp-kicker">THE SPIRIT OF TOGETHERNESS</span><h2>House championship</h2></div><button onClick={() => onNavigate('arena')}>Arena ↗</button></div>{scoreState}<Arena data={data} house={house} compact /><p className="cp-section-note">Every verified contribution makes a difference.</p></section>}</div>
    <CampUpdates key={participant.registration_item_id} item={participant.registration_item_id} compact onReadMore={() => onNavigate('announcements')} />
  </>
}
