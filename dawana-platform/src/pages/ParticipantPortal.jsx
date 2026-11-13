import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { createRequestScope, assertParticipantAccess } from '../services/requestScope'
import { participantRequest, participantDeliveryOptions } from '../services/participantApi'
import { participantOrders, participantExpiry } from '../services/participantPayload'
import './ParticipantPortal.css'
import '../components/dic/CamperExperience.css'
import DigitalIDPresentation from '../components/dic/DigitalIDPresentation'
import CamperExperience from '../components/dic/CamperExperience'
import CamperBrand from '../components/dic/CamperBrand'
import { PortalLoginChoices } from '../components/dic/PortalPhase3'
import { sessionPersistenceLabel } from '../services/portalPhase3'
import { PortalCredentialLogin, PortalAccountSettings } from '../components/dic/PortalAccountAccess'
import { oauthReturn } from '../services/portalAccount'
import { participantSessionClosed, reopenParticipantSession, notifyParticipantSessionClosed, subscribeParticipantSessionClosed, revokeParticipantSession } from '../services/participantSession'

export function ParticipantIDCard({ card, onClose, staff = false }) {
  return <DigitalIDPresentation card={card} onClose={onClose} staff={staff} />
}

export function ParticipantDeliveryStatus({ phase, channels, error, onRetry }) {
  if (phase === 'loading') return <p className="participant-notice" role="status">Checking secure code delivery availability…</p>
  if (phase === 'error') return <div className="participant-error" role="alert"><p>Could not check secure code delivery availability. {error}</p><button className="button" type="button" onClick={onRetry}>Retry delivery check</button></div>
  if (!channels.some(channel => channel.available)) return <p className="participant-notice" role="status">Secure code delivery is not currently available. Please contact authorized DIC staff. No code will be shown on this page.</p>
  return null
}

export function ParticipantAuthStatus({ retryUntil, now, error, phase, channels, deliveryError, onRetry }) {
  if (retryUntil) {
    const seconds = Math.max(0, Math.ceil((retryUntil - now) / 1000))
    return <div className="participant-error" role="alert"><p>{seconds ? `Too many requests. Try again in ${seconds} seconds.` : 'You can try secure access again now.'}</p><button className="button" type="button" disabled={seconds > 0} onClick={onRetry}>{seconds ? `Wait ${seconds}s` : 'Retry secure access'}</button></div>
  }
  if (error) return <div className="participant-error" role="alert"><p>{error}</p><button className="button" type="button" onClick={onRetry}>Retry secure access</button></div>
  return <ParticipantDeliveryStatus phase={phase} channels={channels} error={deliveryError} onRetry={onRetry} />
}

export default function ParticipantPortal() {
  const location = useLocation()
  const [oauthReturned] = useState(() => oauthReturn(location.hash))
  const [profile, setProfile] = useState(null)
  const [checking, setChecking] = useState(() => !participantSessionClosed() || oauthReturn(location.hash))
  const [orders, setOrders] = useState([])
  const [channels, setChannels] = useState([])
  const [deliveryPhase, setDeliveryPhase] = useState('loading')
  const [deliveryError, setDeliveryError] = useState('')
  const [deliveryAttempt, setDeliveryAttempt] = useState(0)
  const [sessionAttempt, setSessionAttempt] = useState(0)
  const [retryUntil, setRetryUntil] = useState(0)
  const [channel, setChannel] = useState('email')
  const [reference, setReference] = useState(() => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(location.state?.bookingReference || '') ? location.state.bookingReference : '')
  const [loginOpen, setLoginOpen] = useState(false)
  const [rememberDevice, setRememberDevice] = useState(false)
  const [capabilities, setCapabilities] = useState(null)
  const [contact, setContact] = useState('')
  const [challenge, setChallenge] = useState(null)
  const [code, setCode] = useState('')
  const [resendAt, setResendAt] = useState(0)
  const [codeExpiresAt, setCodeExpiresAt] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(() => location.hash.startsWith('#verify-email=') ? 'Recover your existing booking or contact DIC support to complete account verification.' : location.hash === '#signin=failed' ? 'Use your username and password, or recover your booking.' : participantSessionClosed() ? 'Sign in again to continue.' : '')
  const [card, setCard] = useState(null)
  const [selection,setSelection] = useState('')
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutFailed,setLogoutFailed] = useState(false)
  const logoutPending = useRef(false)
  const actionPending = useRef(false)
  const [access] = useState(() => createRequestScope())
  const deadline = useRef(null)
  useEffect(() => {
    if (location.hash.startsWith('#verify-email=')) {
      window.history.replaceState(window.history.state, '', window.location.pathname+window.location.search)
    }
  }, [location.hash])
  useEffect(() => {
    if (oauthReturned) {
      // A callback hint is removed and never treated as identity or access.
      window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search)
    }
  }, [oauthReturned, location.hash])

  const clearSensitive = useCallback(() => {
    deadline.current = null
    setProfile(null); setOrders([]); setCard(null); setChallenge(null)
    setSelection('')
    setCode(''); setContact(''); setReference(''); setRememberDevice(false); setLoginOpen(false); setBusy(false); setChecking(false)
  }, [])
  const assertAccess = useCallback((ticket) => {
    assertParticipantAccess(access, ticket, deadline.current, () => window.dispatchEvent(new Event('participant-session-expired')))
  }, [access])
  const read = useCallback(async (ticket, path, body, { notifyExpiry = true } = {}) => {
    assertAccess(ticket)
    const data = await participantRequest(path, body, { signal: ticket.signal, notifyExpiry })
    assertAccess(ticket)
    return data
  }, [assertAccess])
  const load = async (ticket) => {
    const data = await read(ticket, '/enrollments/')
    assertAccess(ticket)
    setOrders(participantOrders(data))
  }
  useEffect(() => {
    const controller = new AbortController()
    participantRequest('/auth/capabilities/', undefined, { signal: controller.signal, notifyExpiry: false })
      .then(data => { if (!controller.signal.aborted) setCapabilities(data) })
      .catch(() => { if (!controller.signal.aborted) setError('Could not load sign-in options. Please retry.') })
    return () => controller.abort()
  }, [sessionAttempt])
  useEffect(() => {
    if (!loginOpen && !challenge) return undefined
    const options = new AbortController()
    participantDeliveryOptions({ signal: options.signal, refresh: deliveryAttempt > 0 }).then((availableChannels) => {
      if (!options.signal.aborted) {
        setChannels(availableChannels); setChannel(availableChannels.find(c => c.available)?.value || '')
        setDeliveryPhase('ready'); setDeliveryError('')
      }
    }).catch((e) => { if (!options.signal.aborted) {
      setDeliveryPhase('error'); setDeliveryError(e.status === 429 ? '' : e.message)
      if (e.status === 429) setRetryUntil(current => Math.max(current, e.retryAt || Date.now() + 60000))
    } })
    return () => options.abort()
  }, [deliveryAttempt, loginOpen, challenge])
  useEffect(() => {
    const ticket = access.begin()
    const expire = () => {
      access.invalidate(); clearSensitive(); setError(''); setLoggingOut(false)
      setNotice('Your participant session has expired. Please verify again.')
    }
    const closed = () => {
      access.invalidate(); clearSensitive(); setError(''); setLoggingOut(false)
      setNotice('Signed out.'); setLogoutFailed(false)
    }
    const unsubscribe = subscribeParticipantSessionClosed(closed)
    window.addEventListener('participant-session-expired', expire)
    // A missing/expired cookie on arrival is a normal signed-out state. Later
    // protected requests still publish expiry and clear all sensitive UI state.
    if (!participantSessionClosed() || oauthReturned) read(ticket, '/enrollments/', undefined, { notifyExpiry: false }).then((result) => {
      assertAccess(ticket)
      deadline.current = participantExpiry(result)
      assertAccess(ticket)
      if (oauthReturned) reopenParticipantSession()
      const orders = participantOrders(result)
      setProfile(result); setOrders(orders)
    }).catch((e) => { if (access.current(ticket) && e.status !== 403 && e.status !== 401) {
      if (e.status === 429) setRetryUntil(current => Math.max(current, e.retryAt || Date.now() + 60000))
      else setError(e.message)
    } })
      .finally(() => { if (access.current(ticket)) setChecking(false) })
    return () => { access.invalidate(); unsubscribe(); window.removeEventListener('participant-session-expired', expire) }
  }, [access, assertAccess, clearSensitive, read, sessionAttempt, oauthReturned])
  useEffect(() => {
    if (!profile) return undefined
    const timer = window.setTimeout(() => window.dispatchEvent(new Event('participant-session-expired')), Math.max(0, new Date(profile.expires_at).getTime() - Date.now()))
    return () => window.clearTimeout(timer)
  }, [profile])
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])

  const perform = async (action) => {
    if (actionPending.current || Date.now() < retryUntil) return
    actionPending.current = true
    const ticket = access.begin()
    setBusy(true); setError(''); setRetryUntil(0)
    try { await action(ticket) } catch (e) { if (access.current(ticket) && e.name !== 'AbortError') {
      if (e.status === 429) { setRetryUntil(e.retryAt || Date.now() + 60000); setNotice('') }
      else setError(e.message)
    } }
    finally { actionPending.current = false; if (access.current(ticket)) { setBusy(false); setLoggingOut(false) } }
  }
  const requestCode = (event) => {
    event?.preventDefault()
    if (Date.now() < retryUntil || (challenge && Date.now() < resendAt)) return
    if (deliveryPhase !== 'ready' || !channels.some(c => c.available)) {
      setError('Secure code delivery must be available before requesting a verification code.')
      return
    }
    return perform(async (ticket) => {
      const data = await read(ticket, '/auth/challenges/', { channel, contact, order_reference: reference })
      assertAccess(ticket)
      setChallenge(data.challenge_id); setCode(''); setNotice(data.detail); setResendAt(Date.now() + data.resend_after * 1000)
      setCodeExpiresAt(Date.now() + data.expires_in * 1000)
    })
  }
  const verify = (event) => {
    event.preventDefault()
    return perform(async (ticket) => {
      const result = await read(ticket, '/auth/verify/', { challenge_id: challenge, code, remember_device: rememberDevice })
      assertAccess(ticket)
      deadline.current = participantExpiry(result)
      reopenParticipantSession(); setLogoutFailed(false)
      assertAccess(ticket)
      setCode(''); setChallenge(null); setContact(''); setReference(''); setNotice(''); setProfile(result)
      await load(ticket)
    })
  }
  const logout = () => {
    if (logoutPending.current) return
    logoutPending.current = true
    let logoutTicket
    return revokeParticipantSession({
      clear: () => { access.invalidate(); clearSensitive(); logoutTicket=access.begin(); setError(''); setNotice(''); setLogoutFailed(false); setLoggingOut(true); notifyParticipantSessionClosed() },
      revoke: () => participantRequest('/auth/logout/', {}, {signal:logoutTicket.signal}),
      success: () => { if(access.current(logoutTicket)) { setNotice('Signed out.'); setLogoutFailed(false) } },
      failure: () => { if(access.current(logoutTicket)) { setNotice('Participant information has been cleared, but server sign-out could not be confirmed. Retry sign-out. On a shared device, close all participant tabs and the browser when finished.'); setLogoutFailed(true) } },
    }).finally(() => { logoutPending.current = false; if(access.current(logoutTicket))setLoggingOut(false) })
  }
  const openID = (participant) => perform(async (ticket) => {
    const id = participant.id
    if (!id || !participant.eligibility.eligible || participant.issue?.status !== 'current') {
      setNotice('No active eligible ID is available. Please contact authorized DIC staff.')
      return
    }
    const data = await read(ticket, `/enrollments/${id}/id/`)
    assertAccess(ticket)
    setCard({ ...data, id })
    window.scrollTo(0, 0)
  })

  const retryAccess = () => {
    if (Date.now() < retryUntil || actionPending.current) return
    setRetryUntil(0); setError('')
    if (deliveryPhase === 'error') { setDeliveryPhase('loading'); setDeliveryError(''); setDeliveryAttempt(value => value + 1) }
    if (!profile) setSessionAttempt(value => value + 1)
  }
  const recoverAccount = (intent) => {
    access.invalidate(); clearSensitive(); setLoginOpen(true); setError('')
    if (intent === 'setup') setChannel('email')
    setNotice(intent === 'reset' ? 'Verify the booking contact below, then set a new password in Sign-in settings.' : 'Verify the booking contact below, then create or link your sign-in account in Sign-in settings.')
  }
  const passwordLogin = credentials => perform(async ticket => {
    const result = await read(ticket, '/auth/password/login/', credentials, { notifyExpiry: false })
    deadline.current = participantExpiry(result); reopenParticipantSession(); setLogoutFailed(false)
    setProfile(result); setNotice(''); await load(ticket)
  })
  const transitionCredentials = credentials => perform(async ticket => {
    const result = await read(ticket, '/auth/credentials/transition/', credentials, { notifyExpiry: false })
    setNotice(result.detail)
  })

  if (checking) return <section className="participant-portal cp-access-loading" aria-busy="true"><CamperBrand /><div className="cp-loading-indicator" aria-hidden="true" /><h1>Opening your Camper Portal</h1><p role="status">Loading your registrations…</p></section>
  return <section className={`participant-portal ${profile ? 'cp-authenticated' : 'cp-auth'} ${card ? 'is-printing-card' : ''}`}>
    {!profile && <div className="participant-page-heading"><Link to="/dic" className="cp-auth-brand"><CamperBrand /></Link><h1>Participant sign in</h1></div>}
    {!profile && (loginOpen || challenge || Boolean(error) || retryUntil > 0) && <ParticipantAuthStatus retryUntil={retryUntil} now={now} error={error} phase={deliveryPhase} channels={channels} deliveryError={deliveryError} onRetry={retryAccess} />}{profile && error && <p className="participant-error" role="alert">{error}</p>}{notice && !retryUntil && <p className="participant-notice" role="status">{notice}</p>}
    {!profile && logoutFailed && <button className="button" disabled={loggingOut} onClick={logout}>{loggingOut?'Signing out…':'Retry server sign-out'}</button>}
    {!profile ? <div className="participant-access-panel">{challenge && <><h2>Check your inbox</h2><p>Enter the six-digit code sent through {channels.find(c => c.value === channel)?.label || 'your selected channel'} if your booking details match.</p></>}
      {!challenge && <PortalCredentialLogin capabilities={capabilities} recoveryAvailable={deliveryPhase === 'ready' && channels.some(c => c.available)} recoveryLoading={loginOpen && deliveryPhase === 'loading'} onCheckRecovery={!loginOpen && deliveryPhase === 'loading' ? () => recoverAccount('reset') : undefined} busy={busy || loggingOut || now < retryUntil} onLogin={passwordLogin} onRecover={recoverAccount} onTransition={transitionCredentials} />}
      <PortalLoginChoices showGoogle={false} open={loginOpen || Boolean(challenge)} onVerify={() => { if (challenge) { setChallenge(null); setCode(''); setNotice(''); setLoginOpen(false) } else setLoginOpen(value => !value) }} />
      {(loginOpen || challenge) && <form id="cp-booking-verification" onSubmit={challenge ? verify : requestCode}>
        {!challenge ? <><label>Booking reference<input required value={reference} onChange={(e) => setReference(e.target.value)} autoComplete="off" placeholder="Full reference from your registration" /></label><label>Contact channel<select required value={channel} onChange={(e) => setChannel(e.target.value)}><option value="" disabled>Select a configured channel</option>{channels.map((c) => <option key={c.value} value={c.value} disabled={!c.available}>{c.label}{!c.available ? ' — unavailable' : ''}</option>)}</select></label><label>Registered primary contact<input required maxLength={254} type={channel === 'email' ? 'email' : 'tel'} value={contact} onChange={(e) => setContact(e.target.value)} autoComplete={channel === 'email' ? 'email' : 'tel'} /></label></> : <label>Six-digit verification code<input required autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} /></label>}
        <button className="button" disabled={busy || loggingOut || now < retryUntil || deliveryPhase !== 'ready' || !channels.some((c) => c.available)}>{busy ? 'Please wait…' : challenge ? 'Verify secure access' : 'Send verification code'}</button>
        {challenge && <label className="cp-remember-device"><input type="checkbox" checked={rememberDevice} disabled={!capabilities?.session?.remember_seconds} onChange={event => setRememberDevice(event.target.checked)} />Keep me signed in on this personal device (up to {sessionPersistenceLabel(capabilities?.session?.remember_seconds || 1800)}). Do not use on shared devices.</label>}
      </form>}{challenge && <><p className="cp-code-expiry" role="status">{now < codeExpiresAt ? `Code expires in ${Math.floor((codeExpiresAt - now) / 60000)}:${String(Math.floor((codeExpiresAt - now) / 1000) % 60).padStart(2, '0')}` : 'This code has expired. Request a new code.'}</p><div className="portal-id-actions"><button disabled={busy || now < resendAt || now < retryUntil} onClick={() => requestCode()}>{now < resendAt ? `Resend in ${Math.ceil((resendAt - now) / 1000)}s` : 'Resend code'}</button><button disabled={busy} onClick={() => { setChallenge(null); setCode(''); setNotice('') }}>Change booking details</button></div></>}
      <p className="cp-auth-help"><Link to="/dic/register/recover">Recover your booking</Link></p>
    </div> : <>
      {card ? <ParticipantIDCard card={card} onClose={() => setCard(null)} /> : <CamperExperience orders={orders} selection={selection} onSelect={value => { access.invalidate(); setCard(null); setSelection(value) }} busy={busy} onOpenID={openID} onLogout={logout} onRefreshBookings={() => perform(load)} loggingOut={loggingOut} expiresAt={profile.expires_at} accountSettings={<PortalAccountSettings capabilities={capabilities} busy={busy} onVerify={() => recoverAccount('setup')} run={action => perform(ticket => action((path, body) => read(ticket, path, body)))} />} />}
    </>}
  </section>
}
