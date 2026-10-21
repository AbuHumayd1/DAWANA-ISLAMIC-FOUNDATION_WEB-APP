import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { getRecoveryChannels } from '../services/dicApi'
import { callbackLookup, paymentReturnFailureKind, resolvePaymentReturn } from '../services/paymentReturnApi'
import '../components/dic/RegistrationControls.css'
import './PaymentReturn.css'

export default function PaymentReturnRoute() {
  const { pathname } = useLocation()
  return <PaymentReturnPage key={pathname} />
}

function PaymentReturnPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { orderId } = useParams()
  const [initial] = useState(() => {
    try { return { lookup: callbackLookup(location.search, orderId) } }
    catch (error) { return { error: error.message } }
  })
  const [lookup, setLookup] = useState(initial.lookup || {})
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(!initial.error)
  const [error, setError] = useState(initial.error || '')
  const [failureKind, setFailureKind] = useState(initial.error ? 'invalid' : null)
  const [recoveryAvailable, setRecoveryAvailable] = useState(null)
  const generation = useRef(0)

  const check = useCallback(async () => {
    const current = ++generation.current
    setBusy(true)
    setError('')
    setFailureKind(null)
    let selectingOrder = false
    try {
      const data = await resolvePaymentReturn(lookup)
      if (generation.current !== current) return
      if (data.orders?.length === 1) { selectingOrder = true; setLookup({ order_id: data.orders[0].order_id }); return }
      setResult(data)
      if (data.order?.payment_status === 'paid' && !orderId) {
        navigate(`/dic/register/confirmation/${data.order.order_id}`, { replace: true })
      }
    } catch (failure) {
      if (generation.current === current) {
        setResult(null)
        const kind = paymentReturnFailureKind(failure)
        setFailureKind(kind)
        setError(kind === 'temporary'
          ? 'The registration service is temporarily unavailable. Your payment status could not be checked. Do not pay again.'
          : kind === 'authorization'
            ? 'Secure access could not be validated. Sign in through the staging tester access page if required, then retry. No payment outcome has been assumed.'
            : kind === 'limited' ? 'Too many status checks. Please wait before retrying. No payment outcome has been assumed.'
              : 'This secure return session or payment reference is unavailable. Recover the existing registration securely.')
      }
    } finally { if (generation.current === current && !selectingOrder) setBusy(false) }
  }, [lookup, navigate, orderId])

  useEffect(() => {
    // Remove callback hints from the visible URL; no URL value authorizes access.
    if (location.search) navigate(location.pathname, { replace: true })
    if (initial.error) return undefined
    let mounted = true
    queueMicrotask(() => { if (mounted) check() })
    return () => { mounted = false; generation.current += 1 }
    // The initial hint is captured once, before the query string is removed.
  }, [check, initial.error]) // eslint-disable-line react-hooks/exhaustive-deps

  const missing = !busy && !result?.order && !result?.orders?.length && (!failureKind || failureKind === 'missing' || failureKind === 'invalid')
  useEffect(() => {
    if (!missing) return undefined
    let active = true
    getRecoveryChannels().then((data) => { if (active) setRecoveryAvailable(data.channels.some((channel) => channel.available)) })
      .catch(() => { if (active) setRecoveryAvailable(false) })
    return () => { active = false }
  }, [missing])

  const order = result?.order
  const paid = order?.payment_status === 'paid'
  const inactive = order?.payment_status === 'refunded' || order?.status === 'cancelled'
  const failed = !order?.verification_unavailable && (order?.attempt_status === 'failed' || order?.payment_status === 'failed')
  const review = ['amount_mismatch', 'reconcile'].includes(order?.attempt_status)
  const title = busy ? 'Checking your payment' : failureKind === 'temporary' ? 'Payment status temporarily unavailable' : failureKind === 'authorization' ? 'Secure access required' : failureKind === 'limited' ? 'Please wait before checking again' : paid ? 'DIC registration confirmed'
    : inactive ? 'Registration payment status' : review ? 'Payment needs review' : failed ? 'Payment not completed'
      : order ? 'Payment awaiting confirmation' : result?.orders?.length ? 'Choose your registration' : 'Recover your registration'

  return <section className="dic-summary dic-payment-return"><Container><div className="confirmation-box" aria-busy={busy}>
    <span className="eyebrow">DARUL ISLAM CAMP · SECURE PAYMENT RETURN</span>
    <h1>{title}</h1>
    {busy && <p role="status">Please wait while Dawana retrieves your registration and checks its authoritative payment status.</p>}
    {error && <p className="dic-flow-message is-error" role="alert">{error}</p>}
    {!busy && ['temporary', 'authorization', 'limited'].includes(failureKind) && <button type="button" className="button" onClick={check}>Retry payment status check</button>}
    {!busy && order && <>
      <p role="status">{paid ? 'Your payment has been confirmed by the registration service.' : inactive ? 'This registration is not available for another payment through this page.' : review ? 'The payment evidence requires review by the DIC registration team. Do not pay again.' : failed ? 'This payment attempt was not successful. No new attempt has been created.' : 'Payment has not been confirmed. Do not pay again while the existing attempt is being checked.'}</p>
      {order.verification_unavailable && <p role="status">The provider could not be reached for verification. The status below is the current Dawana record; please check again later.</p>}
      <dl className="dic-return-details"><dt>Registration reference</dt><dd>{order.order_id}</dd><dt>Payment status</dt><dd>{order.payment_status}</dd><dt>{paid ? 'Paid amount' : 'Order amount'}</dt><dd>{new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(Number(order.total_amount_ngn))}</dd></dl>
      <ul className="dic-confirmation-participants">{order.participants.map((participant, index) => <li key={index}><strong>{participant.name}</strong><span>{participant.category}</span>{participant.occupation && <span>Occupation: {participant.occupation}; marital status: {participant.marital_status}</span>}</li>)}</ul>
      {!paid && !inactive && <button type="button" className="button" onClick={check}>Check existing payment again</button>}
      <p><Link to={`/dic/register/confirmation/${order.order_id}`}>Open this registration’s secure status page</Link></p>
      <p>This status page is available in this browser while its secure return session is valid. Use verified contact recovery after the session expires.</p>
    </>}
    {!busy && result?.orders?.length > 0 && <ul className="dic-return-orders">{result.orders.map((item) => <li key={item.order_id}><p>{item.edition_name} · {item.payment_status}</p><small>{item.order_id}</small><button className="button button-outline" type="button" onClick={() => setLookup({ order_id: item.order_id })}>View registration</button></li>)}</ul>}
    {missing && <><p>This tab could not authorize access to the existing registration. Your payment has not been treated as failed. Return to the original registration tab or use secure contact recovery. Do not create another registration or pay again.</p><p>{recoveryAvailable === false ? 'Automated contact recovery is currently unavailable. Contact the DIC registration team for assistance; ownership must be verified before registration details can be disclosed.' : 'Contact recovery will require verification through an available delivery method.'}</p><Link className="button button-outline" to="/dic/register/recover">Recover existing registration</Link></>}
    {!busy && <p><Link to="/dic">Return to DIC</Link></p>}
  </div></Container></section>
}
