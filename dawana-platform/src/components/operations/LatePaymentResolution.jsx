import { useRef, useState } from 'react'
import { getOperationsData, postOperationsData } from '../../services/operationsApi'

export default function LatePaymentResolution({ reference, onUpdated }) {
  const [decision, setDecision] = useState('reinstate'), [reason, setReason] = useState(''), [refund, setRefund] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [history, setHistory] = useState(null)
  const submission = useRef(null), pending = useRef(false)
  const path = `/payments/${encodeURIComponent(reference)}/resolve/`
  const submit = async event => {
    event.preventDefault()
    if (pending.current) return
    const body = { decision, reason, ...(decision === 'refund_confirmed' ? { provider_refund_id: refund } : {}) }
    const signature = JSON.stringify(body)
    if (submission.current?.signature !== signature) submission.current = { signature, request_id: crypto.randomUUID() }
    pending.current = true; setBusy(true); setError('')
    try {
      await postOperationsData(path, { ...body, request_id: submission.current.request_id })
      setHistory((await getOperationsData(path)).decisions); onUpdated?.()
    } catch (e) { setError(e.message) } finally { pending.current = false; setBusy(false) }
  }
  return <details><summary>Resolve late payment: {reference}</summary><p>Reinstatement grants eligible access. A refund decision records intent only; arrange the refund separately in Paystack. Confirmation verifies an existing full refund and never initiates one.</p>
    <form onSubmit={submit}><fieldset disabled={busy}><label>Decision<select value={decision} onChange={e => setDecision(e.target.value)}><option value="reinstate">Reinstate verified booking</option><option value="refund_requested">Record refund decision</option><option value="refund_confirmed">Verify completed refund</option></select></label>
      <label>Reason<textarea required maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} /></label>
      {decision === 'refund_confirmed' && <label>Paystack refund ID<input required inputMode="numeric" pattern="[0-9]+" maxLength={64} value={refund} onChange={e => setRefund(e.target.value)} /></label>}
      <button className="button" type="submit">{busy ? 'Recording…' : 'Record decision'}</button></fieldset></form>
    <button type="button" disabled={busy} onClick={async () => { try { setHistory((await getOperationsData(path)).decisions) } catch (e) { setError(e.message) } }}>View decision history</button>
    {error && <p role="alert">{error}</p>}{history && <ul>{history.map(row => <li key={row.request_id}>{row.decision.replaceAll('_', ' ')} · {row.reason} · Staff {row.actor_id} · {new Date(row.created_at).toLocaleString()}</li>)}</ul>}
  </details>
}
