import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { privacyPayload } from '../../services/registrationPrivacy'

const base = `${(import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')}/dic/tutor-registration`

export default function TutorRegistration({ invitation, ParticipantForm }) {
  const csrf = useRef('')
  const started = useRef(false)
  const [verification, setVerification] = useState(null)
  const [identity, setIdentity] = useState(null)
  const [code, setCode] = useState('')
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
        setVerification(await request('challenges', { invitation }))
      } catch (failure) { setError(failure.message) }
    })()
  }, [invitation])
  async function verify(event) {
    event.preventDefault(); setBusy(true); setError('')
    try { setIdentity(await request('verify', { verification_id: verification.verification_id, code })) }
    catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  async function save(person) {
    if (busy) return
    setBusy(true); setError('')
    const now = new Date()
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    try {
      const participant = { full_name: person.fullName, address: person.address, phone: person.phone,
        email: person.email, sex: person.sex, academic_status: person.academicStatus,
        occupation: person.occupation, marital_status: person.maritalStatus, ...privacyPayload(person, today) }
      setResult(await request('redeem', { verification_id: verification.verification_id, participant }))
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <div className="dic-flow"><div className="container">
    <h1>Complimentary Tutor Registration — No Payment Required</h1>
    {error && <p role="alert">{error}</p>}
    {result ? <><p>Registration confirmed. Keep your booking reference: <strong>{result.order_id}</strong></p><Link to="/dic/participant" state={{ bookingReference: result.order_id }}>Open participant portal</Link><p>Use your authorized email and booking reference. Digital ID issuance requires authorized staff.</p></>
      : identity ? <fieldset disabled={busy}><ParticipantForm tutor initial={{ fullName: identity.name, email: identity.email, ageChoice: '' }} categories={[]} options={identity.edition} onBack={() => window.location.assign('/dic')} onSave={save} /></fieldset>
        : verification ? <form onSubmit={verify}><p>{verification.detail} Codes and verified access expire after ten minutes. Reopen your invitation to request another code.</p><label>Verification code<input required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={event => setCode(event.target.value)} /></label><button disabled={busy}>Verify authorized email</button></form>
          : <p>{error ? 'Reopen your invitation or contact the authorizing administrator.' : 'Checking tutor invitation…'}</p>}
  </div></div>
}
