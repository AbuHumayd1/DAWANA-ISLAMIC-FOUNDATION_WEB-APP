import { useState } from 'react'
import './StaffPasswordChange.css'

export default function StaffPasswordChange({ onChangePassword, onClose }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (next !== confirm) {
      setError('New passwords do not match.')
      return
    }
    setWorking(true)
    try {
      await onChangePassword(current, next, confirm)
      setSuccess(true)
      setCurrent(''); setNext(''); setConfirm('')
    } catch (failure) {
      setError(failure?.message || 'Password could not be changed.')
    } finally {
      setWorking(false)
    }
  }

  return <div className="staff-password-overlay" role="presentation">
    <section className="staff-password-dialog" role="dialog" aria-modal="true" aria-labelledby="staff-password-title">
      <header>
        <div><small>ACCOUNT SECURITY</small><h2 id="staff-password-title">Change your password</h2></div>
        <button type="button" onClick={onClose} aria-label="Close password settings">✕</button>
      </header>
      {success ? <div role="status" className="staff-password-success">
        <p>Your password has been changed. Use your new password the next time you sign in.</p>
        <button type="button" onClick={onClose}>Done</button>
      </div> : <>
        <p>Choose a memorable password or passphrase you can keep private. Your current password is required.</p>
        <form onSubmit={submit}>
          <label>Current password<input autoFocus type="password" autoComplete="current-password" value={current} onChange={event => setCurrent(event.target.value)} required maxLength={256} /></label>
          <label>New password<input type="password" autoComplete="new-password" value={next} onChange={event => setNext(event.target.value)} required maxLength={256} /></label>
          <label>Confirm new password<input type="password" autoComplete="new-password" value={confirm} onChange={event => setConfirm(event.target.value)} required maxLength={256} /></label>
          {error && <p role="alert" className="staff-password-error">{error}</p>}
          <button type="submit" disabled={working}>{working ? 'Updating…' : 'Update password'}</button>
        </form>
      </>}
    </section>
  </div>
}
