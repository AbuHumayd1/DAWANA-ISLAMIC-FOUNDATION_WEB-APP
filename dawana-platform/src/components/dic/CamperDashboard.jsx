import { Link } from 'react-router-dom'
import { eligibilityLabel } from '../../services/participantIdentity'
import { camperKey,selectedCamper } from '../../services/camperSelection'
import CamperScores from './CamperScores'

export default function CamperDashboard({orders,selection,onSelect,busy,onOpenID}) {
  const selected=selectedCamper(orders,selection)
  if(!selected)return <p>No bookings are currently authorised for this session. Verify the correct booking or contact authorised staff.</p>
  const {order,participant}=selected
  const colour=participant.house_assignment?.colour
  return <div className="camper-dashboard"><label className="camper-selector">Camper<select value={selected.key} disabled={busy} onChange={event=>onSelect(event.target.value)}>
    {orders.flatMap(booking=>booking.participants.map(person=><option key={camperKey(booking,person)} value={camperKey(booking,person)}>{person.name} — {booking.edition}</option>))}
  </select></label>
    <section className="participant-booking"><h2>Booking summary</h2><p>{order.edition}</p><p className="participant-reference">Booking {order.reference}</p><p>Registration: {order.status} · Payment: {order.payment_status}</p></section>
    <section className="participant-summary" aria-live="polite"><h2>{participant.name}</h2><p>{participant.category}</p><p>{participant.participant_number||'Participant number awaiting staff preparation'}</p>
      <div className="camper-status-grid"><section><h3>House assignment</h3><p className="camper-house">{participant.house_assignment?.name&&colour&&/^#[0-9a-fA-F]{6}$/.test(colour)&&<span className="camper-house-colour" style={{backgroundColor:colour}} aria-hidden="true"/>}{participant.house_assignment?.name||'Not yet assigned'}</p></section>
        <section><h3>Camp check-in</h3><p>{participant.checked_in===true?'Checked in':participant.checked_in===false?'Not checked in':'Check-in status unavailable'}</p></section></div>
      <p>{eligibilityLabel(participant.eligibility.code)}</p><p>ID: {participant.issue?.status||'Not issued'}</p>
      <button className="button" disabled={busy||!participant.id||!participant.eligibility.eligible||participant.issue?.status!=='current'} onClick={()=>onOpenID(participant)}>{participant.issue?.status==='current'?'My Digital ID':'Awaiting active ID'}</button>
    </section><nav className="portal-id-actions" aria-label="Camper links"><Link to="/dic#showcase-activities-title">Camp activities</Link><Link to="/dic/feedback">Give Camp Feedback</Link></nav>
    <CamperScores key={selected.key} item={participant.registration_item_id} />
  </div>
}
