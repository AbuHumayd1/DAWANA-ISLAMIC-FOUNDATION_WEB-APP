import { Link } from 'react-router-dom'
import { campDate } from '../../services/dicPresentation'
import { ClassAssignmentCard } from './PortalPhase3'
import EarnPoints from './EarnPoints'

export function CamperProfile({ participant: p, order, ID, Icon, onOpenID, busy }) {
  const tutor = p.registration_basis === 'tutor'
  return <>
    <section className="cw-profile-pass"><div className="cw-pass-top"><span className="cp-kicker">MY CAMPER WORLD</span><Icon name="id" /></div><div className="cw-profile-person"><span className="cp-avatar" aria-hidden="true">{p.name?.slice(0, 1)}</span><div><h1>{p.name}</h1><p>{p.category}</p></div></div><div className="cw-pass-bottom"><span>{p.participant_number || 'Participant number pending'}</span><span>DIC 2026</span></div></section>
    <div className="cw-profile-grid"><section className="cw-info-card cp-tone-mint"><Icon name="arena" /><span className="cp-kicker">{tutor ? 'Your role' : 'Your community'}</span><h2>{tutor ? 'Camp tutor' : p.house_assignment?.name || 'House assignment pending'}</h2>{tutor && <p>Complimentary DIC tutor: no payment required</p>}</section><ClassAssignmentCard participant={p} /></div>
    <section className="cw-booking-summary"><div className="cp-card-title"><h2>Ready for camp</h2><Icon name="day" /></div><dl className="cw-status-chips"><div><dt>Registration</dt><dd>{order.status}</dd></div><div><dt>Payment</dt><dd>{order.payment_status}</dd></div><div><dt>Camp check-in</dt><dd>{p.checked_in === true ? 'Checked in' : p.checked_in === false ? 'Not checked in' : 'Status unavailable'}</dd></div></dl><details className="cw-quiet-details"><summary>Booking details</summary><p>{order.edition}</p><p className="participant-reference">{order.reference}</p></details></section>
    <ID participant={p} onOpenID={onOpenID} busy={busy} />
  </>
}

export function CamperExplore({ participant, camp, onNavigate, Icon }) {
  return <>
    <section className="cw-explore-banner"><div><span className="cp-kicker">A WORLD OF POSSIBILITIES</span><h1>Find your next<br />camp moment.</h1><p>Learn something. Meet someone.<br />Make a memory.</p></div><Icon name="explore" /></section>
    <div className="cw-discover-grid">
      <Link className="cw-discover-card cp-tone-coral" to="/dic#showcase-activities-title"><Icon name="explore" /><span className="cw-card-arrow" aria-hidden="true">↗</span><span className="cp-kicker">Discover</span><h2>Explore approved camp activities</h2><p>Something to look forward to.</p></Link>
      <button className="cw-discover-card cp-tone-yellow" onClick={() => onNavigate('announcements')}><Icon name="feedback" /><span className="cw-card-arrow" aria-hidden="true">↗</span><span className="cp-kicker">Stay connected</span><h2>Camp announcements</h2><p>The latest from your camp.</p></button>
      <button className="cw-discover-card cp-tone-sky" onClick={() => onNavigate('feedback')}><Icon name="feedback" /><span className="cw-card-arrow" aria-hidden="true">↗</span><span className="cp-kicker">Your voice matters</span><h2>Feedback & care</h2><p>Feedback, complaints and support.</p></button>
      <button className="cw-discover-card cp-tone-mint" onClick={() => onNavigate('day')}><Icon name="day" /><span className="cw-card-arrow" aria-hidden="true">↗</span><span className="cp-kicker">Make the most of it</span><h2>Your camp programme</h2><p>Activities and shared meals.</p></button>
    </div>
    <section className="cw-care-links"><div className="cp-card-title"><h2>A camp that cares</h2><Icon name="feedback" /></div><div>{[['daily','Daily feedback'],['welfare','Submit a complaint'],['history','Complaint status'],['final','Final camp evaluation']].map(([channel,label]) => <Link key={channel} to={`/dic/feedback?channel=${channel}`}>{label}<span aria-hidden="true">↗</span></Link>)}</div></section>
    <section className="cw-camp-note"><Icon name="camp" /><div><h2>Good to know</h2>{camp ? <><p>{campDate(camp.camp_start_date)} – {campDate(camp.camp_end_date)}</p><p>{camp.venue || 'Venue to be announced'}</p></> : <p>Edition dates and venue are available on the official camp page when configured.</p>}</div></section>
    {participant.registration_basis !== 'tutor' && <details className="cw-quiet-details"><summary>House duties & camp notices</summary><p>House duty details are not available in the current portal. Follow approved announcements and ask your camp officers for guidance.</p></details>}
  </>
}

export function CamperArena({ participant: p, data, scoreState, onRefresh, onPage, Arena, Contributions, Icon }) {
  const house = p.house_assignment?.name
  return <>
    <section className="cw-arena-banner"><div><span className="cp-kicker">THE HOUSE CHAMPIONSHIP</span><h1>One camp.<br />A shared spirit.</h1><p>Every verified contribution counts.</p></div><span className="cw-trophy" aria-hidden="true"><Icon name="trophy" /></span></section>
    {scoreState}
    <section className="cw-championship"><div className="cp-card-title"><div><span className="cp-kicker">TOGETHER, WE RISE</span><h2>House championship</h2></div><button className="cp-text-button" onClick={onRefresh}>Refresh standings ↻</button></div><Arena data={data} house={house} /></section>
    <div className="cw-arena-personal"><section className="cw-info-card cp-tone-lavender"><Icon name="arena" /><span className="cp-kicker">Your house</span><h2>{house || 'Your house assignment will appear here.'}</h2><p>A community to belong to.</p></section><section className="cw-info-card cp-tone-mint"><Icon name="points" /><span className="cp-kicker">Verified individual points</span><strong className="cw-own-points">{data?.ready ? data.total : '—'}</strong><button className="cp-text-button" onClick={onRefresh}>Refresh points ↻</button></section></div>
    <EarnPoints catalogue={data?.earn_points} />
    <section className="cw-contribution-section"><div className="cp-card-title"><h2>Contribution history</h2><Icon name="points" /></div>{data?.ready && <Contributions rows={data.history} />}{data?.count > data?.page_size && <div className="cp-pagination"><button disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Previous awards</button><span>{data.page} / {Math.ceil(data.count / data.page_size)}</span><button disabled={data.page * data.page_size >= data.count} onClick={() => onPage(data.page + 1)}>Next awards</button></div>}</section>
    <details className="cw-quiet-details"><summary>Our house, our contributions</summary>{data?.ready && data.house ? <ol className="cp-arena" aria-label="My house individual leaderboard">{data.house_leaderboard.map((row, index) => <li key={index} className={row.own ? 'cp-own-house' : ''}><span className="cp-rank">{row.rank}</span><strong>{row.name}{row.own && ' · You'}</strong><b>{row.points}</b></li>)}</ol> : <p>Individual rankings are available only within your assigned house.</p>}<p className="cp-section-note">Current members’ contributions credited to this house. Earlier contributions stay with the original house.</p></details>
  </>
}
