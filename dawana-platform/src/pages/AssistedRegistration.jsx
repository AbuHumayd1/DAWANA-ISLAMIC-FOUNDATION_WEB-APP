import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getOperationsData, postOperationsData } from '../services/operationsApi'
import { getRegistrationOptions, getRecoveryChannels } from '../services/dicApi'
import { occupations, maritalOptions } from '../components/dic/participantOptions'
import { assistedPreparationPath, preparationPayload, assistedBookingPayload, academicStatuses } from '../services/assistedRegistration'
import './AssistedRegistration.css'

export function PayerHandoffGuide({ channels = null, enabled = false }) {
  const available = (channels || []).filter(channel => channel.available)
  return <section className="ops-panel"><h2>Let the payer use their own device</h2>
    <p>{enabled ? 'Authorized officers may create a booking below. Payment and private booking access remain with the payer through contact verification.' : 'Staff-created bookings are not enabled. This page checks details only; it cannot create a registration or start a payment.'}</p>
    <ol><li>{enabled ? 'After saving an assisted booking, open /dic/register/recover on the payer’s own device. Do not create another public registration for the same campers.' : <>For a new booking, open <Link to="/dic/register">DIC registration</Link> on the payer’s own device. Use the camper’s or responsible registrant’s contact, not the officer’s.</>}</li>
      <li>If a booking already exists, use <Link to="/dic/register/recover">Recover existing registration</Link> with its registered primary contact. Resume that booking instead of creating another.</li>
      <li>The payer privately verifies their contact, reviews the current price and completes the existing Paystack checkout. Do not share officer cookies, browser storage, OTPs or booking-access tokens.</li>
      <li>Only backend-verified payment establishes paid eligibility. A screenshot, browser redirect or prepared-details result is not payment evidence or camp admission.</li></ol>
    <p>{channels === null ? 'Recovery channel status has not loaded yet.' : available.length ? `Recovery channels reported available: ${available.map(channel => channel.label).join(', ')}. Delivery must still succeed on the payer’s device.`
      : 'No recovery delivery channel is currently reported available. Existing-booking handoff needs an approved working channel; staff cannot bypass contact verification.'}</p>
    <p className="ops-small-note">For another phone, use the approved reachable website address. A laptop’s localhost address is not reachable as that same address on the payer’s phone.</p>
  </section>
}

function Input({ name, label, type = 'text', required = true, ...props }) {
  return <label>{label}<input name={name} type={type} required={required} autoComplete="off" {...props} /></label>
}
function Select({ name, label, choices }) {
  return <label>{label}<select name={name} required><option value="">Choose…</option>{choices.map(item => {
    const value = typeof item === 'string' ? item : item.value
    return <option key={value} value={value}>{typeof item === 'string' ? item : item.label}</option>
  })}</select></label>
}

export function AssistedPreparationForm({ categories = [], busy = false, onSubmit, onChange, canCreate = false, locked = false }) {
  const [count, setCount] = useState(1)
  return <form className="ops-panel assisted-preparation-form" autoComplete="off" onSubmit={onSubmit} onInput={onChange} onReset={onChange}>
    <h2>{canCreate ? 'Create a paid camper booking' : 'Check required details — no booking created'}</h2>
    <p>{canCreate ? 'Create one booking for this payer and their campers. Existing server pricing and eligibility checks apply. No payment is started; the payer must verify their contact privately to resume checkout.' : 'Optional preparation for one camper. Details remain in this page only and are sent for field checks; they are not saved as a draft. Category eligibility and final pricing are checked when the existing registration flow creates the order.'}</p>
    {Array.from({ length: count }, (_, index) => <fieldset key={index} disabled={busy || locked}><legend>Camper {index + 1} details</legend>
      <label>Registration category<select required name="category_id"><option value="">Choose…</option>{categories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      <Input name="full_name" label="Full name" maxLength={200} /><Input name="address" label="Address" />
      <Input name="phone" label="Camper phone" type="tel" maxLength={32} /><Input name="email" label="Camper email" type="email" />
      <Input name="date_of_birth" label="Exact date of birth" type="date" />
      <Select name="sex" label="Sex" choices={['Male', 'Female']} />
      <Input name="height_cm" label="Height (cm)" type="number" min="0.01" step="0.01" />
      <Input name="weight_kg" label="Weight (kg)" type="number" min="0.01" step="0.01" />
      <Select name="academic_status" label="Academic status" choices={academicStatuses} />
      <Select name="occupation" label="Occupation" choices={occupations} /><Select name="marital_status" label="Marital status" choices={maritalOptions} />
    </fieldset>)}
    {canCreate && <button type="button" className="ops-button" disabled={busy || locked || count >= 10} onClick={() => { setCount(value => value + 1); onChange?.() }}>Add another camper</button>}
    <fieldset disabled={busy || locked}><legend>Payer / responsible registrant</legend>
      <Input name="payer_name" label="Name" maxLength={200} /><Input name="payer_email" label="Own recovery email" type="email" required={false} />
      <Input name="payer_phone" label="Own recovery phone" type="tel" maxLength={32} required={false} />
      <p>At least one working payer recovery contact is required. Do not request the payer’s OTP, card details or PIN.</p>
    </fieldset>
    {canCreate && <p>Confirm the payer supplied these details and owns the recovery contact. If a booking might already exist, use payer recovery first. Do not submit again with a new request after an uncertain response.</p>}
    <button className="ops-button ops-button-primary" disabled={busy || !categories.length}>{canCreate ? locked ? 'Retry same booking request' : 'Confirm and create booking' : 'Check details only'}</button>
    <button className="ops-button ops-button-secondary" type="reset" disabled={busy || locked}>Clear private details</button>
  </form>
}

export default function AssistedRegistration() {
  const [data, setData] = useState(null), [error, setError] = useState(''), [message, setMessage] = useState('')
  const [revision, retry] = useState(0), [busy, setBusy] = useState(false)
  const pending = useRef(null)
  const [locked, setLocked] = useState(false), [saved, setSaved] = useState(null)
  useEffect(() => {
    let live = true
    Promise.all([getOperationsData(assistedPreparationPath), getRegistrationOptions(), getRecoveryChannels()])
      .then(([mode, options, recovery]) => { if (live) { setData({ mode, options, recovery }); setError('') } })
      .catch(() => { if (live) setError('Registration preparation could not load. Retry or use the existing payer registration/recovery pages.') })
    return () => { live = false }
  }, [revision])
  async function check(event) {
    event.preventDefault(); setMessage(''); setError('')
    const form = event.currentTarget
    const canCreate = data?.mode.can_create_assisted
    let payload
    try {
      payload = canCreate ? pending.current || assistedBookingPayload(new FormData(form), crypto.randomUUID()) : preparationPayload(Object.fromEntries(new FormData(form)))
      if (canCreate) { pending.current = payload; setLocked(true) }
    }
    catch (failure) { setError(failure.message); return }
    setBusy(true)
    try {
      const result = await postOperationsData(assistedPreparationPath + (canCreate ? 'create/' : ''), payload)
      setMessage(result.message)
      if (canCreate) { form.reset(); pending.current = null; setSaved(result) }
    } catch (failure) {
      if (canCreate && failure.status === 400) {
        pending.current = null; setLocked(false)
        setError(failure.message || 'Details were rejected. No booking was saved; check the fields or use payer recovery.')
      } else setError(canCreate ? 'Booking could not be confirmed. Retry the same request. Do not create a second booking; ask the payer to check recovery if this remains unresolved.' : 'Some details failed field checks or your staff session is unavailable. No booking was created by this page.')
    }
    finally { setBusy(false) }
  }
  return <div className="assisted-preparation">
    <div className="ops-page-heading"><div><span className="ops-eyebrow">Registration assistance</span><h1>Prepare camper registration</h1><p>Help a camper complete the existing paid registration on their own device.</p></div></div>
    <PayerHandoffGuide channels={data?.recovery.channels ?? null} enabled={data?.mode.can_create_assisted} />
    {error && <p className="ops-error" role="alert">{error}<button type="button" disabled={busy} onClick={() => { setData(null); setError(''); retry(value => value + 1) }}>Retry</button></p>}
    {message && <p role="status">{message}</p>}
    {saved && <section className="ops-panel"><h2>Booking saved — payment pending</h2><p>Assistance reference: {saved.assistance_id}</p><p>Saved: {saved.created_at}</p><p>On the payer’s own device open /dic/register/recover and privately verify the contact entered. This reference grants no booking access.</p></section>}
    {!data && !error && <p role="status">Loading registration preparation…</p>}
    {data?.options.registration_is_open && ['preparation_only', 'assisted_creation'].includes(data?.mode.mode)
      ? !saved && <AssistedPreparationForm categories={data.options.categories} busy={busy} locked={locked} canCreate={data.mode.can_create_assisted} onSubmit={check} onChange={() => setMessage('')} />
      : data && <p>Preparation is unavailable or registration is closed. This page cannot override registration windows or enable staff-created bookings.</p>}
  </div>
}
