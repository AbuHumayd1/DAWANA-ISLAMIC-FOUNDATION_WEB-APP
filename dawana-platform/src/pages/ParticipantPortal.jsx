import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { createRequestScope, assertParticipantAccess } from '../services/requestScope'
import { participantRequest } from '../services/participantApi'
import './ParticipantPortal.css'
import { eligibilityLabel } from '../services/participantIdentity'

export function ParticipantIDCard({ card, onClose }) {
  return <section className="participant-id-view" aria-label="Individual participant ID">
    <div className="participant-print-controls"><button className="button" onClick={() => window.print()}>Print this ID</button><button className="button" onClick={onClose}>Back to participants</button></div>
    {!card.branding_verified && <p className="participant-notice" role="status">Official logo asset pending. This card has not received final branding or print-layout acceptance.</p>}
    <article className="participant-id-card">
      <header>{card.logo_url && <img src={card.logo_url} alt="Dawana Islamic Foundation official logo" />}<div><strong>Dawana Islamic Foundation</strong><p>{card.edition}</p></div></header>
      <div className="participant-id-content"><span>Participant identification</span><h2>{card.name}</h2><p className="participant-id-number">{card.participant_number}</p>
        {card.category && <p><strong>Category:</strong> {card.category}</p>}{card.house && <p><strong>House:</strong> {card.house}</p>}
        <p><strong>Camp:</strong> {new Date(`${card.starts}T12:00:00`).toLocaleDateString('en-GB')} – {new Date(`${card.ends}T12:00:00`).toLocaleDateString('en-GB')}</p><p><strong>Venue:</strong> {card.venue}</p>
      </div><footer>Issue {card.version} · Identification only. Staff must verify current validity. This card does not authorize camp entry or departure.</footer>
    </article>
  </section>
}

export default function ParticipantPortal() {
  const [profile, setProfile] = useState(null)
  const [checking, setChecking] = useState(true)
  const [orders, setOrders] = useState([])
  const [channels, setChannels] = useState([])
  const [channel, setChannel] = useState('email')
  const [reference, setReference] = useState('')
  const [contact, setContact] = useState('')
  const [challenge, setChallenge] = useState(null)
  const [code, setCode] = useState('')
  const [resendAt, setResendAt] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [card, setCard] = useState(null)
  const [loggingOut, setLoggingOut] = useState(false)
  const [access] = useState(() => createRequestScope())
  const deadline = useRef(null)

  const clearSensitive = useCallback(() => {
    deadline.current = null
    setProfile(null); setOrders([]); setCard(null); setChallenge(null)
    setCode(''); setContact(''); setReference(''); setBusy(false); setChecking(false)
  }, [])
  const assertAccess = useCallback((ticket) => {
    assertParticipantAccess(access, ticket, deadline.current, () => window.dispatchEvent(new Event('participant-session-expired')))
  }, [access])
  const read = useCallback(async (ticket, path, body) => {
    assertAccess(ticket)
    const data = await participantRequest(path, body, { signal: ticket.signal })
    assertAccess(ticket)
    return data
  }, [assertAccess])
  const load = async (ticket) => {
    const data = await read(ticket, '/enrollments/')
    assertAccess(ticket)
    setOrders(data.orders)
  }
  useEffect(() => {
    const ticket = access.begin()
    const options = new AbortController()
    participantRequest('/auth/options/', undefined, { signal: options.signal }).then((result) => {
      if (!options.signal.aborted) { setChannels(result.channels); setChannel(result.channels.find((c) => c.available)?.value || '') }
    }).catch((e) => { if (!options.signal.aborted) setError(e.message) })
    const expire = () => {
      access.invalidate(); clearSensitive(); setError(''); setLoggingOut(false)
      setNotice('Your participant session has expired. Please verify again.')
    }
    window.addEventListener('participant-session-expired', expire)
    read(ticket, '/auth/me/').then(async (result) => {
      assertAccess(ticket)
      deadline.current = Date.parse(result.expires_at)
      const data = await read(ticket, '/enrollments/')
      assertAccess(ticket)
      setProfile(result); setOrders(data.orders)
    }).catch((e) => { if (access.current(ticket) && e.status !== 403 && e.status !== 401) setError(e.message) })
      .finally(() => { if (access.current(ticket)) setChecking(false) })
    return () => { access.invalidate(); options.abort(); window.removeEventListener('participant-session-expired', expire) }
  }, [access, assertAccess, clearSensitive, read])
  useEffect(() => {
    if (!profile) return undefined
    const timer = window.setTimeout(() => window.dispatchEvent(new Event('participant-session-expired')), Math.max(0, new Date(profile.expires_at).getTime() - Date.now()))
    return () => window.clearTimeout(timer)
  }, [profile])
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])

  const perform = async (action) => {
    const ticket = access.begin()
    setBusy(true); setError('')
    try { await action(ticket) } catch (e) { if (access.current(ticket) && e.name !== 'AbortError') setError(e.message) }
    finally { if (access.current(ticket)) { setBusy(false); setLoggingOut(false) } }
  }
  const requestCode = (event) => {
    event?.preventDefault()
    return perform(async (ticket) => {
      const data = await read(ticket, '/auth/challenges/', { channel, contact, order_reference: reference })
      assertAccess(ticket)
      setChallenge(data.challenge_id); setCode(''); setNotice(data.detail); setResendAt(Date.now() + data.resend_after * 1000)
    })
  }
  const verify = (event) => {
    event.preventDefault()
    return perform(async (ticket) => {
      const result = await read(ticket, '/auth/verify/', { challenge_id: challenge, code })
      assertAccess(ticket)
      deadline.current = Date.parse(result.expires_at)
      assertAccess(ticket)
      setCode(''); setChallenge(null); setContact(''); setReference(''); setNotice(''); setProfile(result)
      await load(ticket)
    })
  }
  const logout = () => {
    access.invalidate(); clearSensitive(); setNotice(''); setLoggingOut(true)
    return perform(async (ticket) => {
      await read(ticket, '/auth/logout/', {})
      assertAccess(ticket)
      setNotice('You have securely signed out.')
    })
  }
  const openID = (participant) => perform(async (ticket) => {
    let id = participant.id
    if (!participant.issue) {
      const enrollment = await read(ticket, '/enrollments/', { registration_item_id: participant.registration_item_id })
      id = enrollment.id
      await load(ticket)
    }
    const data = await read(ticket, `/enrollments/${id}/id/`)
    assertAccess(ticket)
    setCard(data)
    window.scrollTo(0, 0)
  })

  if (checking) return <section className="participant-portal container" aria-busy="true"><p role="status">Checking secure participant access…</p></section>
  return <section className={`participant-portal container ${card ? 'is-printing-card' : ''}`}>
    <div className="participant-page-heading"><div><span className="eyebrow">Daarul Islam Camp</span><h1>Participant portal</h1><p>Secure access to your booking and individual participant IDs.</p></div><Link className="text-link" to="/dic">Back to DIC</Link></div>
    {error && <p className="participant-error" role="alert">{error}</p>}{notice && <p className="participant-notice" role="status">{notice}</p>}
    {!profile ? <div className="participant-access-panel"><h2>Verify your booking</h2><p>Use your full booking reference and the primary email address or phone number registered with it. Contact verification does not establish guardianship or collection authority.</p>
      {!channels.some((c) => c.available) && <p className="participant-notice">Secure code delivery is not currently available. Please contact authorized DIC staff. No code will be shown on this page.</p>}
      <form onSubmit={challenge ? verify : requestCode}>
        {!challenge ? <><label>Booking reference<input required value={reference} onChange={(e) => setReference(e.target.value)} autoComplete="off" placeholder="Full reference from your registration" /></label><label>Contact channel<select required value={channel} onChange={(e) => setChannel(e.target.value)}><option value="" disabled>Select a configured channel</option>{channels.map((c) => <option key={c.value} value={c.value} disabled={!c.available}>{c.label}{!c.available ? ' — unavailable' : ''}</option>)}</select></label><label>Registered primary contact<input required maxLength={254} type={channel === 'email' ? 'email' : 'tel'} value={contact} onChange={(e) => setContact(e.target.value)} autoComplete={channel === 'email' ? 'email' : 'tel'} /></label></> : <label>Six-digit verification code<input required autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} /></label>}
        <button className="button" disabled={busy || loggingOut || !channels.some((c) => c.available)}>{busy ? 'Please wait…' : challenge ? 'Verify secure access' : 'Send verification code'}</button>
      </form>{challenge && <div className="portal-id-actions"><button disabled={busy || now < resendAt} onClick={() => requestCode()}>{now < resendAt ? `Resend in ${Math.ceil((resendAt - now) / 1000)}s` : 'Resend code'}</button><button disabled={busy} onClick={() => { setChallenge(null); setCode(''); setNotice('') }}>Change booking details</button></div>}
    </div> : <>
      <div className="participant-session"><span>Verified booking access · expires {new Date(profile.expires_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span><div className="portal-id-actions"><button className="button" disabled={busy} onClick={() => perform(load)}>Refresh registrations</button><button className="button" disabled={loggingOut} onClick={logout}>Secure logout</button></div><p>This session covers the verified booking. Sign out to verify a different booking.</p></div>
      {card ? <ParticipantIDCard card={card} onClose={() => setCard(null)} /> : <><h2>My registrations and participants</h2>{orders.length === 0 ? <p>No bookings are currently authorized for this session. Verify the correct booking or contact authorized staff.</p> : orders.map((order) => <article className="participant-booking" key={order.reference}><header><h3>{order.edition}</h3><p className="participant-reference">Booking {order.reference}</p><p>Registration: {order.status} · Payment: {order.payment_status}</p></header><div className="participant-grid">{order.participants.map((participant) => <article className="participant-summary" key={participant.registration_item_id}><h3>{participant.name}</h3><p>{participant.category}</p><p>{participant.participant_number || 'Individual number assigned on first eligible issuance'}</p><p className="participant-status">{eligibilityLabel(participant.eligibility.code)}</p>{participant.issue && <p>ID: {participant.issue.status} · issue {participant.issue.version}</p>}<button className="button" disabled={busy || !participant.eligibility.eligible || (participant.issue && participant.issue.status !== 'current')} onClick={() => openID(participant)}>{participant.issue ? 'View / print ID' : 'Issue my individual ID'}</button></article>)}</div></article>)}</>}
    </>}
  </section>
}
