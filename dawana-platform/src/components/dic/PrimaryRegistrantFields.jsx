import { PasswordField } from './PortalAccountAccess'
import GuardianFields from './GuardianFields'
import { requiresGuardianContact } from '../../services/guardianContact'

export default function PrimaryRegistrantFields({ contact, onChange, locked, credentials, onCredentials, credentialsLocked, participants, housingReference, readOnly = false, contactOnly = false }) {
  const update = (field, value) => onChange({ ...contact, [field]: value })
  const guardianRequired = requiresGuardianContact(participants)
  return <div className="dic-primary-contact">{readOnly ? <p>Booking contact: {contact?.fullName} · {contact?.email}</p> : <><fieldset disabled={locked}><legend>Booking contact</legend>
    {guardianRequired && <p>For campers below 16 on 23 December 2026, the booking contact must be the responsible parent or guardian. Their name and phone are required.</p>}
    <label className="dic-field"><span>{guardianRequired ? 'Parent or guardian name' : 'Booking contact name'}</span><input required maxLength={200} autoComplete="name" value={contact?.fullName || ''} onChange={event => update('fullName', event.target.value)} /></label>
    <label className="dic-field"><span>Booking email</span><input required type="email" maxLength={254} autoComplete="email" value={contact?.email || ''} onChange={event => update('email', event.target.value)} /></label>
    <label className="dic-field"><span>{guardianRequired ? 'Parent or guardian phone' : 'Booking phone (optional)'}</span><input required={guardianRequired} type="tel" maxLength={32} autoComplete="tel" value={contact?.phone || ''} onChange={event => update('phone', event.target.value)} /></label>
    </fieldset>
    <GuardianFields participants={participants} reference={housingReference} contact={contact} onChange={onChange} locked={locked} />
    </>}
    {!contactOnly && credentials && !credentialsLocked && <fieldset><legend>Participant account</legend>
      <label className="dic-field">Account option<select value={credentials.mode || 'create'} onChange={event => onCredentials({ ...credentials, mode: event.target.value, password: '', password_confirmation: '' })}><option value="create">Create a new participant account</option><option value="existing">Use an existing participant account</option></select></label>
      <label className="dic-field"><span>Username</span><input required maxLength={40} autoComplete="username" value={credentials.username || ''} onChange={event => onCredentials({ ...credentials, mode: credentials.mode || 'create', username: event.target.value })} /></label>
      <PasswordField value={credentials.password} onChange={password => onCredentials({ ...credentials, mode: credentials.mode || 'create', password })} autoComplete={credentials.mode === 'existing' ? 'current-password' : 'new-password'} label={credentials.mode === 'existing' ? 'Existing password' : 'Choose password'} />
      {credentials.mode !== 'existing' && <PasswordField value={credentials.password_confirmation} onChange={password_confirmation => onCredentials({ ...credentials, password_confirmation })} autoComplete="new-password" label="Confirm password" />}
      <small>A longer memorable password helps protect your account. Use your original account and booking contact for additional registrations.</small>
    </fieldset>}
    <p>For additional registrations, select your existing account and use its original booking email.</p>
    {locked && !contact?.email && <p>This older checkout has no saved primary email in this browser. Continue an existing payment only through its saved checkout or <a href="/dic/register/recover">recover the booking</a>. Ask authorized DIC staff to review missing contact details; do not create another registration or pay again.</p>}
  </div>
}
