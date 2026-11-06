import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import './PortalPhase3.css'

export function PasswordField({ value, onChange, autoComplete = 'current-password', label = 'Password', required = true }) {
  const [visible, setVisible] = useState(false)
  return <label>{label}<span className="cp-password-field"><input required={required} minLength={autoComplete === 'new-password' ? 12 : undefined} maxLength={128} type={visible ? 'text' : 'password'} autoComplete={autoComplete} value={value} onChange={event => onChange(event.target.value)} /><button type="button" onClick={() => setVisible(current => !current)} aria-pressed={visible} aria-label={visible ? 'Hide password' : 'Show password'}>{visible ? 'Hide' : 'Show'}</button></span></label>
}

export function PortalCredentialLogin({ capabilities, busy, onLogin, onRecover, onResend }) {
  const [identifier, setIdentifier] = useState(''), [password, setPassword] = useState(''), [remember, setRemember] = useState(false)
  const enabled = capabilities?.accounts?.enabled === true
  return <div className="cp-account-login"><form onSubmit={event => { event.preventDefault(); const secret = password; setPassword(''); onLogin({ identifier, password: secret, remember_device: remember }) }}>
    <fieldset disabled={!enabled || busy}><label>Email or username<input required maxLength={254} autoComplete="username" value={identifier} onChange={event => setIdentifier(event.target.value)} /></label><PasswordField value={password} onChange={setPassword} />
      <label className="cp-remember-device"><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)} />Keep me signed in on this personal device (up to 8 hours). Leave unchecked on shared devices.</label>
      <button className="button" type="submit">{busy ? 'Signing in…' : 'Sign In'}</button></fieldset>
  </form>{!enabled && <p role="status">Password accounts await approved setup. Use your booking verification code.</p>}
    <p>Sign in with your verified booking email and password. Existing usernames are also supported.</p>
    <button type="button" disabled={busy || !enabled || !identifier || !password} onClick={() => { const secret = password; setPassword(''); onResend({ identifier, password: secret }) }}>Resend email verification link</button>
    <div className="portal-id-actions"><button type="button" disabled={busy} onClick={() => onRecover('reset')}>Forgot Password</button><button type="button" disabled={busy} onClick={() => onRecover('setup')}>First-Time Account Setup</button></div>
    <p>Account setup is for older bookings without a registration password. New registrations already create your account; verify your email link, then sign in when your booking is eligible. Authorized complimentary tutors do not need payment.</p>
  </div>
}

export function PortalEmailVerification({ token, run, busy }) {
  const [done, setDone] = useState(false)
  if (!token || done) return done ? <p role="status">Email verified. Sign in with your email and password when your booking is eligible. Ordinary registrations require verified payment; authorized complimentary tutors do not.</p> : null
  return <section className="cp-card"><h2>Verify your email</h2><p>This confirms email ownership only. Paid registration or authorized tutor eligibility is still required.</p><button type="button" className="button" disabled={busy} onClick={() => run(async read => { await read('/auth/email/verify/', { token }); setDone(true) })}>Confirm email ownership</button></section>
}

export function PortalAccountSettings({ capabilities, run, onVerify, busy }) {
  const [status, setStatus] = useState(null), [version, setVersion] = useState(0), [failure, setFailure] = useState(''), [message, setMessage] = useState('')
  const [username, setUsername] = useState(''), [email, setEmail] = useState(''), [password, setPassword] = useState(''), [identifier, setIdentifier] = useState(''), [linkPassword, setLinkPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  useEffect(() => {
    if (!capabilities?.accounts?.enabled) return undefined
    const controller = new AbortController()
    participantRequest('/auth/account/', undefined, { signal: controller.signal }).then(result => { if (!controller.signal.aborted) { setStatus(result); setFailure('') } }).catch(error => { if (!controller.signal.aborted) setFailure(error.message) })
    return () => controller.abort()
  }, [capabilities, version])
  if (!capabilities?.accounts?.enabled) return null
  const submit = (path, body) => { setPassword(''); setPasswordConfirmation(''); setLinkPassword(''); setMessage(''); return run(async read => { await read(path, body); setMessage('Sign-in settings saved. Additional linked bookings appear at your next account sign-in.'); setVersion(current => current + 1) }) }
  return <section className="cp-card cp-account-settings" aria-label="Sign-in settings"><h2>Sign-in settings</h2><p>Only explicitly verified bookings are linked. Sharing an email address does not automatically link children or other bookings.</p>
    {failure && <p role="alert">{failure}</p>}{message && <p role="status">{message}</p>}{!status && !failure && <p role="status">Loading sign-in settings…</p>}
    {status && !status.fresh_otp && <><p>Verify your booking contact again to set up, reset or link a sign-in method.</p><button type="button" className="button" onClick={onVerify}>Verify booking contact</button></>}
    {status?.fresh_otp && <>
      {!status.account ? <><form onSubmit={event => { event.preventDefault(); submit('/auth/account/activate/', { username, email, password, password_confirmation: passwordConfirmation }) }}><fieldset disabled={busy}>
        <label>Choose a username<input required minLength={3} maxLength={40} pattern="[A-Za-z0-9][A-Za-z0-9_.-]{2,39}" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} /></label>
        <label>Verified booking email<input required type="email" maxLength={254} autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} /></label><small>Use the primary booking email you just verified by email OTP. A paid registration is required, except for an authorized complimentary tutor.</small>
        <PasswordField value={password} onChange={setPassword} autoComplete="new-password" label="New password (12–128 characters)" /><PasswordField value={passwordConfirmation} onChange={setPasswordConfirmation} autoComplete="new-password" label="Confirm password" /><button type="submit" className="button">Create sign-in account</button></fieldset></form>
        <p>Already have an account and verified another booking with the same primary contact?</p><form onSubmit={event => { event.preventDefault(); submit('/auth/account/link-booking/', { identifier, password: linkPassword }) }}><fieldset disabled={busy}><label>Existing account email or username<input required maxLength={254} value={identifier} autoComplete="username" onChange={event => setIdentifier(event.target.value)} /></label><PasswordField value={linkPassword} onChange={setLinkPassword} /><button className="button">Link this verified booking</button></fieldset></form></>
        : <><p>Account: {status.account.username}</p><form onSubmit={event => { event.preventDefault(); submit('/auth/password/reset/', { password }) }}><fieldset disabled={busy}><PasswordField value={password} onChange={setPassword} autoComplete="new-password" label="New password (12–128 characters)" /><button className="button">Set or reset password</button></fieldset></form><p>Changing your password signs out other account sessions.</p>
        </>}
    </>}
  </section>
}
