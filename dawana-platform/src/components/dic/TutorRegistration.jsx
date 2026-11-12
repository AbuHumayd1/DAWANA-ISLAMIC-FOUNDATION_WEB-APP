import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { PasswordField } from './PortalAccountAccess'
import { registrationCredentialsPayload } from '../../services/bookingContact'
import { privacyPayload } from '../../services/registrationPrivacy'

const base = `${(import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')}/dic/tutor-registration`

export default function TutorRegistration({ invitation, ParticipantForm }) {
  const csrf = useRef('')
  const started = useRef(false)
  const [verification, setVerification] = useState(null)
  const [identity, setIdentity] = useState(null)
  const [credentials, setCredentials] = useState({ username: '', password: '', password_confirmation: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  async function request(path, body) {
    const response = await fetch(`${base}/${path}/`, { method: body ? 'POST' : 'GET',
      credentials: 'include', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf.current },
      ...(body ? { body: JSON.stringify(body) } : {}) })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Tutor registration could not be completed. Check your details or contact your administrator.')
    return data
  }
  useEffect(() => {
    if (started.current) return
    started.current = true
    ;(async () => {
      try {
        const token = await request('challenges'); csrf.current = token.csrfToken
        const accepted = await request('challenges', { invitation })
        setVerification(accepted)
        if (accepted.verified) setIdentity(accepted)
      } catch (failure) { setError(failure.message) }
    })()
  }, [invitation])
  async function save(person) {
    if (busy) return
    setBusy(true); setError('')
    const now = new Date()
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    try {
      const participant = { full_name: person.fullName, address: person.address, phone: person.phone,
        email: person.email, sex: person.sex, academic_status: person.academicStatus,
        occupation: person.occupation, marital_status: person.maritalStatus, ...privacyPayload(person, today) }
      const portal_account = registrationCredentialsPayload(credentials)
      setCredentials(current => ({ ...current, password: '', password_confirmation: '' }))
      setResult(await request('redeem', { verification_id: verification.verification_id, participant, portal_account }))
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <div className="dic-flow"><div className="container">
    <h1>Complimentary Tutor Registration — No Payment Required</h1>
    {error && <p role="alert">{error}</p>}
    {result ? <><p>Registration confirmed. Keep your booking reference: <strong>{result.order_id}</strong></p><Link to="/dic/participant" state={{ bookingReference: result.order_id }}>Open participant portal</Link><p>Sign in with your username and password. Digital ID issuance requires authorized staff.</p></>
      : identity ? <fieldset disabled={busy}><legend>Portal credentials</legend><label>Username<input required maxLength={40} autoComplete="username" value={credentials.username} onChange={event => setCredentials({ ...credentials, username: event.target.value })} /></label><PasswordField value={credentials.password} onChange={password => setCredentials({ ...credentials, password })} autoComplete="new-password" label="Create password" /><PasswordField value={credentials.password_confirmation} onChange={password_confirmation => setCredentials({ ...credentials, password_confirmation })} autoComplete="new-password" label="Confirm password" /><ParticipantForm tutor initial={{ fullName: identity.name, email: identity.email, ageChoice: '' }} categories={[]} options={identity.edition} onBack={() => window.location.assign('/dic')} onSave={save} /></fieldset>
        : <p>{error || verification ? 'Reopen your invitation or contact the authorizing administrator.' : 'Checking tutor invitation…'}</p>}
  </div></div>
}
