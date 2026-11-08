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
    {credentials && !credentialsLocked && <fieldset><legend>Portal password</legend><PasswordField value={credentials.password} onChange={password => onCredentials({ ...credentials, password })} autoComplete="new-password" label="Create password (or your existing portal password)" /><PasswordField value={credentials.password_confirmation} onChange={password_confirmation => onCredentials({ ...credentials, password_confirmation })} autoComplete="new-password" label="Confirm password" /></fieldset>}
    <p>Create your password now. Verify your email using the one-time email link, then sign in with email and password once your booking is eligible. Ordinary registrations require verified payment; authorized complimentary tutors do not. Existing accounts must use their current password. Registration alone never grants portal access.</p>
    {locked && !contact?.email && <p>This older checkout has no saved primary email in this browser. Continue an existing payment only through its saved checkout or <a href="/dic/register/recover">recover the booking</a>. Ask authorized DIC staff to review missing contact details; do not create another registration or pay again.</p>}
  </div>
}
