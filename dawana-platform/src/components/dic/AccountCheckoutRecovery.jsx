import { useRef, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { PasswordField } from './PortalAccountAccess'
import './AccountCheckoutRecovery.css'

export default function AccountCheckoutRecovery({ onRecovered }) {
  const [username, setUsername] = useState(''), [password, setPassword] = useState('')
  const [orders, setOrders] = useState([]), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const pending = useRef(false)
  const recover = async event => {
    event.preventDefault()
    if (pending.current) return
    pending.current = true; setBusy(true); setError(''); setOrders([])
    const secret = password; setPassword('')
    try {
      const result = await participantRequest('/auth/orders/recover/', { identifier: username, password: secret })
      setOrders(result.orders)
      if (!result.orders.length) setError('No recoverable unpaid bookings are linked to this account. Paid bookings remain in your participant portal.')
    } catch (e) { setError(e.message) } finally { pending.current = false; setBusy(false) }
  }
  return <section className="phase-a-account-recovery" aria-label="Recover with participant account"><h2>Use your participant account</h2>
    <p>Recover an existing checkout without creating another registration.</p>
    <form onSubmit={recover}><fieldset disabled={busy}><label>Username<input required maxLength={40} autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} /></label>
      <PasswordField value={password} onChange={setPassword} /><button className="button" type="submit">{busy ? 'Finding bookings…' : 'Find my unpaid bookings'}</button></fieldset></form>
    {error && <p role="alert">{error}</p>}
    {orders.map(row => <article key={row.order.order_id}><strong>{row.order.edition_name}</strong><p>{row.order.order_id}</p>
      <p>{row.order.lifecycle?.expired ? 'Expired — contact staff if you paid. Do not start another payment.' : 'Unpaid — available to resume'}</p>
      <button type="button" className="button" onClick={() => { onRecovered({ ...row.order, accessToken: row.access_token }); setOrders([]) }}>Open booking status</button></article>)}
  </section>
}
