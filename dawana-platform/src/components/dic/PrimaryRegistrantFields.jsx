import { PasswordField } from './PortalAccountAccess'
import GuardianFields from './GuardianFields'

export default function PrimaryRegistrantFields({ contact, onChange, locked, credentials, onCredentials, credentialsLocked, participants, housingReference }) {
  const update = (field, value) => onChange({ ...contact, [field]: value })
  return <div className="dic-primary-contact"><fieldset disabled={locked}><legend>Primary camper or guardian contact</legend>
    <p>Enter the adult managing this booking and an email you own. Do not substitute a child’s email for the guardian’s contact.</p>
    <label className="dic-field"><span>Primary camper or guardian name</span><input required maxLength={200} autoComplete="name" value={contact?.fullName || ''} onChange={event => update('fullName', event.target.value)} /></label>
    <label className="dic-field"><span>Booking email</span><input required type="email" maxLength={254} autoComplete="email" value={contact?.email || ''} onChange={event => update('email', event.target.value)} /></label>
    <label className="dic-field"><span>Booking phone (optional)</span><input type="tel" maxLength={32} autoComplete="tel" value={contact?.phone || ''} onChange={event => update('phone', event.target.value)} /></label>
    </fieldset>
    <GuardianFields participants={participants} reference={housingReference} contact={contact} onChange={onChange} locked={locked} />
    {credentials && !credentialsLocked && <fieldset><legend>Participant account</legend>
      <label className="dic-field">Account option<select value={credentials.mode || 'create'} onChange={event => onCredentials({ ...credentials, mode: event.target.value, password: '', password_confirmation: '' })}><option value="create">Create a new participant account</option><option value="existing">Use an existing participant account</option></select></label>
      <label className="dic-field"><span>Username</span><input required maxLength={40} autoComplete="username" value={credentials.username || ''} onChange={event => onCredentials({ ...credentials, mode: credentials.mode || 'create', username: event.target.value })} /></label>
      <PasswordField value={credentials.password} onChange={password => onCredentials({ ...credentials, mode: credentials.mode || 'create', password })} autoComplete={credentials.mode === 'existing' ? 'current-password' : 'new-password'} label={credentials.mode === 'existing' ? 'Existing password' : 'Choose password'} />
      {credentials.mode !== 'existing' && <PasswordField value={credentials.password_confirmation} onChange={password_confirmation => onCredentials({ ...credentials, password_confirmation })} autoComplete="new-password" label="Confirm password" />}
      <small>A longer memorable password helps protect your account. Use your original account and booking contact for additional registrations.</small>
    </fieldset>}
    <p>Choose a unique username and password now. Sign in with these credentials once your booking is eligible; no email activation is required. Ordinary registrations require verified payment; authorized complimentary tutors do not. Existing accounts must use their current username and password. Registration alone never grants portal access.</p>
    {locked && !contact?.email && <p>This older checkout has no saved primary email in this browser. Continue an existing payment only through its saved checkout or <a href="/dic/register/recover">recover the booking</a>. Ask authorized DIC staff to review missing contact details; do not create another registration or pay again.</p>}
  </div>
}
