import { useState } from 'react'
import { postOperationsData } from '../../services/operationsApi'
import { PasswordField } from '../dic/PortalAccountAccess'

export default function AccountRecovery({ orderReference }) {
  const [review, setReview] = useState(''), [password, setPassword] = useState('')
  const [token, setToken] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  async function issue(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setToken('')
    const secret = password; setPassword('')
    try {
      const result = await postOperationsData('/account-recovery/', { order_reference: orderReference, review_reference: review, password: secret })
      setToken(result.token)
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <details className="ops-panel"><summary>Authorize participant credential recovery</summary>
    <p>System administrators only. First verify the primary registrant’s ownership through the approved private review process. Record its reference; an email address or payment reference alone is insufficient. Never request or choose the registrant’s password. Privileged accounts use Django Admin’s existing controlled credential workflow.</p>
    {error && <p role="alert">{error}</p>}
    <form onSubmit={issue}><fieldset disabled={busy}><label>Ownership review reference<input required minLength={10} maxLength={240} value={review} onChange={event => setReview(event.target.value)} /></label>
      <PasswordField value={password} onChange={setPassword} label="Your administrator password" />
      <button type="submit" className="ops-button">Issue one-use recovery code</button></fieldset></form>
    {token && <div role="status"><p>Hand this code directly to the reviewed owner through an authorized private channel. It expires in 15 minutes. Enter it under “Recover username access without email” in the participant portal.</p><output>{token}</output><button type="button" onClick={() => setToken('')}>Hide code</button></div>}
  </details>
}
