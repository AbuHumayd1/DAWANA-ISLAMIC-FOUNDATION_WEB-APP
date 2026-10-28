import { useEffect, useState } from 'react'
import { foundationRequest, safeDonationCheckout, newDonationRequest, donationMessage } from '../../services/foundation'

function useOptions() {
  const [state, setState] = useState({ data: null, error: '' }), [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    foundationRequest('/options/', { signal: controller.signal }).then(data => { if (!controller.signal.aborted) setState({ data, error: '' }) })
      .catch(error => { if (!controller.signal.aborted) setState({ data: null, error: error.message }) })
    return () => controller.abort()
  }, [revision])
  return { ...state, retry: () => setRevision(value => value + 1) }
}

export function VerifiedContactInformation() {
  const { data, error, retry } = useOptions(), channels = data?.channels || {}
  return <section className="contact-information"><h2>How to reach us</h2>
    {error && <p role="alert">Contact details could not be loaded. <button onClick={retry}>Retry</button></p>}
    {!data && !error && <p role="status">Loading official contact channels…</p>}
    {data && !Object.keys(channels).length && <p>Verified official contact channels are awaiting confirmation by the Foundation.</p>}
    <div className="contact-details-grid">{channels.email && <article className="contact-detail-card"><h3>Email</h3><a href={'mailto:' + channels.email}>{channels.email}</a></article>}
      {channels.phone && <article className="contact-detail-card"><h3>Telephone</h3><a href={'tel:' + channels.phone}>{channels.phone}</a></article>}
      {channels.phones?.map(phone => <article className="contact-detail-card" key={phone}><h3>Telephone</h3><a href={'tel:' + phone}>{phone}</a></article>)}
      {channels.whatsapp && <article className="contact-detail-card"><h3>WhatsApp</h3><a href={'https://wa.me/' + channels.whatsapp.slice(1)} target="_blank" rel="noopener noreferrer">Open official WhatsApp</a></article>}
      {channels.address && <article className="contact-detail-card"><h3>Address</h3><p>{channels.address}</p></article>}</div>
  </section>
}

export function FoundationContactForm() {
  const { data, error: optionsError, retry } = useOptions()
  const [busy, setBusy] = useState(false), [status, setStatus] = useState(''), [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault(); if (busy) return
    const form = event.currentTarget, values = Object.fromEntries(new FormData(form))
    setBusy(true); setStatus(''); setError('')
    try { await foundationRequest('/contact/', { body: values }); setStatus('Your enquiry has been received by the Foundation inbox.'); form.reset() }
    catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  return <section className="contact-form-panel"><h2>Send an enquiry</h2><p>Your message is available only to authorized Foundation staff. This form is separate from confidential camper welfare reporting.</p>
    {optionsError && <p role="alert">{optionsError} <button onClick={retry}>Retry</button></p>}
    {!data && !optionsError && <p role="status">Checking enquiry availability…</p>}
    {data && !data.contact_enabled && <p>The Foundation enquiry inbox is awaiting activation.</p>}
    {data?.contact_enabled && <form className="contact-form" onSubmit={submit}><div className="contact-form-grid">
      <label>Full name<input name="name" required maxLength={120} autoComplete="name" /></label>
      <label>Email<input name="email" type="email" required maxLength={254} autoComplete="email" /></label>
      <label>Subject<input name="subject" required maxLength={200} /></label>
      <label className="contact-form-full">Message<textarea name="message" required minLength={10} maxLength={5000} rows={5} /></label>
      <label hidden aria-hidden="true">Website<input name="website" tabIndex={-1} autoComplete="off" /></label>
    </div><button className="button" disabled={busy}>{busy ? 'Sending…' : 'Send enquiry'}</button></form>}
    {status && <p role="status">{status}</p>}{error && <p role="alert">{error}</p>}
  </section>
}

function savedDonation() {
  try { const value = JSON.parse(sessionStorage.getItem('foundation_donation') || 'null'); return value?.request?.request_id && /^[a-f0-9]{64}$/.test(value.request.access_token) ? value : null } catch { return null }
}

export function DonationExperience() {
  const { data: options, error: optionsError, retry } = useOptions()
  const [saved, setSaved] = useState(savedDonation), [payment, setPayment] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  function remember(value) { setSaved(value); try { sessionStorage.setItem('foundation_donation', JSON.stringify(value)) } catch { /* State remains in this tab if storage is unavailable. */ } }
  async function initialize(event) {
    event?.preventDefault(); if (busy) return
    const values = event ? Object.fromEntries(new FormData(event.currentTarget)) : null
    const request = saved?.request || newDonationRequest(values.email, values.amount)
    remember({ request }); setBusy(true); setError('')
    try { const result = await foundationRequest('/donations/', { body: request }); remember({ request, reference: result.reference }); setPayment(result) }
    catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  async function verify() {
    if (busy || !saved?.reference) return
    setBusy(true); setError('')
    try { setPayment(await foundationRequest('/donations/' + encodeURIComponent(saved.reference) + '/', { body: {}, token: saved.request.access_token })) }
    catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  return <aside className="donate-details-card"><h3>Support Dawana</h3><p>Donations are separate from DIC registration fees.</p>
    {optionsError && <p role="alert">{optionsError} <button onClick={retry}>Retry</button></p>}
    {!options && !optionsError && <p role="status">Checking donation availability…</p>}
    {options && !options.donations_enabled && <p>Donation collection is awaiting approved configuration. No payment will be initiated here.</p>}
    {options?.donations_enabled && <><p><strong>Test mode only — no live collection.</strong></p>
      {!saved && <form onSubmit={initialize}><label>Email<input name="email" type="email" required maxLength={254} /></label><label>Amount (NGN)<input name="amount" type="number" step="0.01" required min={options.minimum} max={options.maximum} /></label><p>Any amount from NGN {options.minimum}. No business maximum applies; payment and storage precision limits apply.</p><button className="button" disabled={busy}>Prepare test donation</button></form>}
      {saved && !saved.reference && <button className="button" disabled={busy} onClick={() => initialize()}>Check existing initialization request</button>}
      {saved?.reference && <><p>Reference: {saved.reference}</p><button className="button" disabled={busy} onClick={verify}>{busy ? 'Checking…' : 'Verify payment status'}</button></>}
      {payment && <><p role="status">{donationMessage(payment.status)}</p>{safeDonationCheckout(payment.authorization_url) && <><a className="button" href={payment.authorization_url} target="_blank" rel="noopener noreferrer">Open test checkout</a><p>After checkout, return to this tab and verify payment status.</p></>}
        {['successful', 'failed', 'abandoned'].includes(payment.status) && <button onClick={() => { setSaved(null); setPayment(null); try { sessionStorage.removeItem('foundation_donation') } catch { /* Only this tab's state is reset. */ } }}>Prepare another donation</button>}</>}
    </>}{error && <p role="alert">{error}</p>}
  </aside>
}
