import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { participantRequest } from '../../services/participantApi'
import { continueToPortal, portalIntegrationSlots } from '../../services/portalPhase3'
import './PortalPhase3.css'
import CampUpdates from './CampUpdates'

export function PortalScenery() {
  return <div className="cp-phase3-scenery" aria-hidden="true"><svg viewBox="0 0 800 150" fill="none" focusable="false">
    <defs><pattern id="cp-geometry" width="64" height="64" patternUnits="userSpaceOnUse"><path d="m32 3 9 20 20 9-20 9-9 20-9-20L3 32l20-9Z" /></pattern></defs>
    <path className="cp-geometry" fill="url(#cp-geometry)" d="M0 0h800v150H0z" />
    <path d="M0 134q110-28 215 0t215 0 215 0 155 0M308 126V71q42-48 84 0v55m-67 0V79q25-29 50 0v47M294 126h112M301 67V34m-6 0h12m-6-7v-9M413 126V49m-8 0h16m-13 0V26h10v23M502 127l51-65 51 65Zm51-65v65m-16 0 16-24 16 24M132 127V67m-22 26 22-37 22 37m-49 20 27-44 27 44M662 126V75m-22 23 22-35 22 35m-46 18 24-40 24 40" />
    <path className="cp-gold-line" d="M343 31a13 13 0 1 1 13-19 15 15 0 0 0-13 19ZM73 32l4 8 9 1-7 6 2 9-8-4-8 4 2-9-7-6 9-1ZM728 48l3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1Z" />
  </svg></div>
}

export function PortalLoginChoices({ onVerify, open, showGoogle = false }) {
  return <div className="cp-login-choices">{showGoogle && <><button className="cp-google-button" type="button" disabled aria-describedby="cp-google-unavailable">Continue with Google <span>Unavailable</span></button>
    <p id="cp-google-unavailable">Google sign-in is not configured. Your verified booking contact remains the secure way to sign in.</p></>}
    <button className="button" type="button" onClick={onVerify} aria-expanded={open} aria-controls="cp-booking-verification">{open ? 'Hide booking verification' : 'Use a verification code'}</button>
    <p>Already signed in on this device? We check your existing secure session automatically.</p></div>
}

export function ClassAssignmentCard({ participant }) {
  const tutor = participant.registration_basis === 'tutor'
  // No inferred class from registration category, age, academic status or housing.
  const assignment = participant.class_assignment
  const assigned = assignment?.status === 'assigned' && typeof assignment.name === 'string' && assignment.name.trim()
  return <section className="cp-card cp-class-card"><span className="cp-kicker">LEARNING TOGETHER</span><h2>{tutor ? 'Tutor registration' : 'My Class'}</h2>
    <p className="cw-class-name">{tutor ? 'Camper class allocation does not apply to tutor registrations.' : assigned ? assignment.name : 'Not yet assigned'}</p>
    {!tutor && !assigned && <small>Your class will appear here when it is ready.</small>}</section>
}

export function PortalIntegrations({ participant, onOpenID, busy }) {
  const tutor = participant.registration_basis === 'tutor'
  return <section className="cp-phase3-integrations"><div className="cp-section-heading"><span className="cp-kicker">YOUR CAMP COMPANION</span><h2>Camp essentials</h2><p>Your digital ID is available when issued. Other camp information will appear when approved.</p></div><div className="cp-integration-grid">
    {portalIntegrationSlots.filter(slot => !tutor || !slot.competitiveCamperOnly).map(slot => <section className="cp-card" key={slot.id}><h3>{slot.title}</h3>
      {slot.id === 'id' ? <><p>Issued by authorized DIC staff.</p><button type="button" className="button" disabled={busy || !participant.id || !participant.eligibility?.eligible || participant.issue?.status !== 'current'} onClick={() => onOpenID(participant)}>Open digital ID</button></>
        : ['today', 'timetable', 'food'].includes(slot.id) ? <Link className="button" to="/dic/participant?view=timetables">Open Timetables</Link>
        : slot.channel ? <Link className="button" to={'/dic/feedback?channel='+slot.channel}>Open {slot.title}</Link>
        : <><p>No information is available here yet.</p><span className="cp-future-label">Coming later</span></>}</section>)}
  </div>{participant.registration_item_id && <CampUpdates item={participant.registration_item_id} />}</section>
}

export function PortalContinuation({ orderReference }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  async function proceed() {
    if (busy) return
    setBusy(true); setError('')
    try {
      const state = await continueToPortal(orderReference, participantRequest)
      navigate('/dic/participant', { state })
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <div className="cp-secure-continuation"><button type="button" className="button" disabled={busy} onClick={proceed}>{busy ? 'Checking secure access…' : 'Continue to Camper Portal'}</button><p>Sign in with the username and password chosen during registration. No email activation is required. Payment confirmation alone does not sign you in. Older registrations can use authorized account recovery.</p>{error && <p role="alert">{error}</p>}</div>
}
