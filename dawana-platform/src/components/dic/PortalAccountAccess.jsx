import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import './PortalPhase3.css'

export function PasswordField({ value, onChange, autoComplete = 'current-password', label = 'Password', required = true }) {
  const [visible, setVisible] = useState(false)
  return <label>{label}<span className="cp-password-field"><input aria-label={label} required={required} maxLength={128} type={visible ? 'text' : 'password'} autoComplete={autoComplete} value={value} onChange={event => onChange(event.target.value)} /><button type="button" onClick={() => setVisible(current => !current)} aria-pressed={visible} aria-label={visible ? 'Hide password' : 'Show password'}>{visible ? 'Hide' : 'Show'}</button></span></label>
}

export function PortalCredentialLogin({ capabilities, busy, onLogin, onRecover, onTransition, recoveryAvailable = false, recoveryLoading = false, onCheckRecovery }) {
  const [identifier, setIdentifier] = useState(''), [password, setPassword] = useState(''), [remember, setRemember] = useState(false)
  const enabled = capabilities?.accounts?.enabled === true
  return <div className="cp-account-login"><form onSubmit={event => { event.preventDefault(); const secret = password; setPassword(''); onLogin({ identifier, password: secret, remember_device: remember }) }}>
    <fieldset disabled={!enabled || busy}><label>Username<input required maxLength={40} autoComplete="username" value={identifier} onChange={event => setIdentifier(event.target.value)} /></label><PasswordField value={password} onChange={setPassword} />
      <label className="cp-remember-device"><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)} />Keep me signed in on this personal device (up to 8 hours). Leave unchecked on shared devices.</label>
      <button className="button" type="submit">{busy ? 'Signing in…' : 'Sign In'}</button></fieldset>
  </form>{!enabled && <p role="status">Password accounts await approved setup. Contact authorized DIC staff if secure booking verification is unavailable.</p>}
    <PortalCredentialRecovery busy={busy || !enabled} onSubmit={onTransition} />
    {recoveryAvailable ? <div className="portal-id-actions"><button type="button" disabled={busy} onClick={() => onRecover('reset')}>Forgot Password</button><button type="button" disabled={busy} onClick={() => onRecover('setup')}>First-Time Account Setup</button></div> : onCheckRecovery ? <><p>Recover access using your booking contact.</p><button type="button" className="cp-text-button" disabled={busy} onClick={onCheckRecovery}>Forgot your sign-in details?</button></> : <p role="status">{recoveryLoading ? 'Checking secure recovery options…' : 'Contact DIC support for account recovery.'}</p>}
  </div>
}

export function PortalCredentialRecovery({ busy, onSubmit }) {
  const [token, setToken] = useState(''), [username, setUsername] = useState('')
  const [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState('')
  return <details className="cp-account-recovery"><summary>Recover username access without email</summary>
    <p>Enter the one-use code issued after DIC support verifies your booking. Valid for 15 minutes. Never share your password.</p>
    <form onSubmit={event => { event.preventDefault(); const body = { token, username, password, password_confirmation: confirmation }; setToken(''); setPassword(''); setConfirmation(''); onSubmit(body) }}><fieldset disabled={busy}>
      <label>Administrator-issued recovery code<input required minLength={43} maxLength={43} type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>
      <label>Choose your username<input required maxLength={40} autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} /></label>
      <PasswordField value={password} onChange={setPassword} autoComplete="new-password" label="New password" />
      <PasswordField value={confirmation} onChange={setConfirmation} autoComplete="new-password" label="Confirm password" />
      <button type="submit" className="button">Update credentials</button></fieldset></form>
  </details>
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
  const submit = (path, body) => { setPassword(''); setPasswordConfirmation(''); setLinkPassword(''); setMessage(''); return run(async read => { await read(path, body); setMessage('Account Settings saved. Sign in again to see linked bookings.'); setVersion(current => current + 1) }) }
  return <section className="cp-card cp-account-settings" aria-label="Account Settings"><h2>Account Settings</h2>
    {failure && <p role="alert">{failure}</p>}{message && <p role="status">{message}</p>}{!status && !failure && <p role="status">Loading sign-in settings…</p>}
    {status && !status.fresh_otp && <><p>Verify your booking contact to update account access.</p><button type="button" className="button" onClick={onVerify}>Verify booking contact</button></>}
    {status?.fresh_otp && <>
      {!status.account ? <><form onSubmit={event => { event.preventDefault(); submit('/auth/account/activate/', { username, email, password, password_confirmation: passwordConfirmation }) }}><fieldset disabled={busy}>
        <label>Choose a username<input required maxLength={40} autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} /></label>
        <label>Verified booking email<input required type="email" maxLength={254} autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} /></label><small>Use the booking email you verified.</small>
        <PasswordField value={password} onChange={setPassword} autoComplete="new-password" label="New password (up to 128 characters)" /><PasswordField value={passwordConfirmation} onChange={setPasswordConfirmation} autoComplete="new-password" label="Confirm password" /><button type="submit" className="button">Create sign-in account</button></fieldset></form>
        <p>Already have an account and verified another booking with the same primary contact?</p><form onSubmit={event => { event.preventDefault(); submit('/auth/account/link-booking/', { identifier, password: linkPassword }) }}><fieldset disabled={busy}><label>Existing account email or username<input required maxLength={254} value={identifier} autoComplete="username" onChange={event => setIdentifier(event.target.value)} /></label><PasswordField value={linkPassword} onChange={setLinkPassword} /><button className="button">Link this verified booking</button></fieldset></form></>
        : <><p>Account: {status.account.username}</p><form onSubmit={event => { event.preventDefault(); submit('/auth/password/reset/', { password }) }}><fieldset disabled={busy}><PasswordField value={password} onChange={setPassword} autoComplete="new-password" label="New password (up to 128 characters)" /><button className="button">Set or reset password</button></fieldset></form><p>Changing your password signs out other account sessions.</p>
        </>}
    </>}
  </section>
}
