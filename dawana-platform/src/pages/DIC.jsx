import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import CategorySelection from '../components/dic/CategorySelection'
import Field, { RegistrationSelect } from '../components/dic/RegistrationField'
import {
  createRegistrationOrder,
  acceptOrderPricing,
  getRegistrationOptions,
  getRegistrationOrder,
  getRecoveryChannels,
  getRecoveryOrders,
  initializePayment,
  requestRecoveryCode,
  resendRecoveryCode,
  restoreRecoveredOrder,
  verifyPayment,
  verifyRecoveryCode,
} from '../services/dicApi'

const SESSION_KEY = 'dawana.dic.registration.v1'
const DRAFT_LIFETIME_MS = 30 * 60 * 1000

const emptyParticipant = {
  fullName: '',
  address: '',
  phone: '',
  email: '',
  dob: '',
  sex: '',
  height: '',
  weight: '',
  academicStatus: '',
  occupation: '',
  maritalStatus: '',
  categoryId: '',
}
const academicOptions = ['Primary Student', 'Secondary Student', 'Tertiary Student', 'Graduate / Completed Tertiary Education', 'Not Currently in School']
const occupations = ['Civil Servant', 'Business', 'Trader', 'Entrepreneur']
const maritalOptions = ['Single', 'Married', 'Divorcee', 'Widow / Widower']
const routeFor = { landing: '/dic', form: '/dic/register', summary: '/dic/register/summary', checkout: '/dic/register/checkout', confirmation: '/dic/register/confirmation' }

function newUuidV4() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function emptyFlow() {
  return {
    participants: [],
    idempotencyKey: newUuidV4(),
    orderId: null,
    orderSummary: null,
    paymentReference: null,
    paymentStatus: 'pending',
    submissionUncertain: false,
    expiresAt: Date.now() + DRAFT_LIFETIME_MS,
  }
}

function loadFlow() {
  try {
    const saved = sessionStorage.getItem(SESSION_KEY)
    if (!saved) return { flow: emptyFlow(), storageAvailable: true, expired: false }
    const parsed = JSON.parse(saved)
    const valid = parsed
      && Array.isArray(parsed.participants)
      && typeof parsed.idempotencyKey === 'string'
      && typeof parsed.expiresAt === 'number'
      && parsed.expiresAt > Date.now()
    if (!valid) {
      sessionStorage.removeItem(SESSION_KEY)
      return { flow: emptyFlow(), storageAvailable: true, expired: true }
    }
    return {
      flow: { ...emptyFlow(), ...parsed },
      storageAvailable: true,
      expired: false,
    }
  } catch {
    return { flow: emptyFlow(), storageAvailable: false, expired: false }
  }
}

function saveFlow(flow) {
  try {
    const orderSummary = flow.orderSummary
      ? {
        order_id: flow.orderSummary.order_id,
        status: flow.orderSummary.status,
        payment_status: flow.orderSummary.payment_status,
        currency: flow.orderSummary.currency,
        total_amount_ngn: flow.orderSummary.total_amount_ngn,
        participant_count: flow.orderSummary.participant_count,
        items: (flow.orderSummary.items || []).map((item) => ({
          category_name: item.category_name || item.category_name_snapshot,
          fee_ngn: item.fee_ngn ?? item.fee_snapshot_ngn,
          price_type: item.price_type,
        })),
      }
      : null
    sessionStorage.setItem(
      SESSION_KEY,
      JSON.stringify({
        participants: flow.participants,
        idempotencyKey: flow.idempotencyKey,
        orderId: flow.orderId,
        orderSummary,
        paymentReference: flow.paymentReference,
        paymentStatus: flow.paymentStatus,
        submissionUncertain: flow.submissionUncertain,
        expiresAt: Date.now() + DRAFT_LIFETIME_MS,
      }),
    )
    return true
  } catch {
    return false
  }
}

function clearSavedFlow() {
  try {
    sessionStorage.removeItem(SESSION_KEY)
  } catch {
    return false
  }
  return true
}

function participantPayload(participant) {
  return {
    category_id: Number(participant.categoryId),
    full_name: participant.fullName,
    address: participant.address,
    phone: participant.phone,
    email: participant.email,
    date_of_birth: participant.dob,
    sex: participant.sex,
    height_cm: participant.height,
    weight_kg: participant.weight,
    academic_status: participant.academicStatus,
    occupation: participant.occupation,
    marital_status: participant.maritalStatus,
  }
}

function formatNgn(amount) {
  const value = Number(amount)
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-NG', {
    style: 'currency',
    currency: 'NGN',
    minimumFractionDigits: 2,
  }).format(value)
}

function formatDate(value) {
  if (!value) return 'To be announced'
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.getTime())
    ? 'To be announced'
    : new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(date)
}

function formatLagosDateTime(value) {
  if (!value) return 'Not configured'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? 'Not configured'
    : new Intl.DateTimeFormat('en-GB', {
      dateStyle: 'long',
      timeStyle: 'short',
      timeZone: 'Africa/Lagos',
    }).format(date)
}

function localDateInputValue() {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function getErrorMessage(error, fallback) {
  if (error?.message) return error.message
  return fallback
}

function paymentReferenceFromError(error) {
  return error?.body?.payment_reference
    || error?.body?.detail?.payment_reference
    || null
}

function FlowMessage({ children, kind = 'info' }) {
  if (!children) return null
  return <p className={`dic-flow-message is-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</p>
}

function RegistrationProgress({ current }) {
  const steps = [['Registration', 'form'], ['Review', 'summary'], ['Checkout', 'checkout'], ['Confirmation', 'confirmation']]
  return <nav className="dic-steps" aria-label="Registration progress">{steps.map(([label, step], index) => <div className={step === current ? 'is-current' : ''} aria-current={step === current ? 'step' : undefined} key={step}><b>0{index + 1}</b><span>{label}</span></div>)}</nav>
}

function DICInfoPanel({ options, optionsState, onRegister, onRetry }) {
  const categories = options?.categories || []
  const canRegister = optionsState === 'ready' && options?.registration_is_open && categories.length > 0
  const status = optionsState === 'loading'
    ? 'Loading registration details…'
    : optionsState === 'error'
      ? 'Registration details are temporarily unavailable.'
      : !options
        ? 'No active DIC edition is currently configured.'
        : !options.registration_is_open
          ? 'Registration is not currently open.'
          : categories.length === 0
            ? 'No registration categories are currently available.'
            : `${categories.length} configured ${categories.length === 1 ? 'category' : 'categories'}`
  const fees = categories
    .map((category) => Number(category.current_fee_ngn))
    .filter((fee, index) => categories[index].current_fee_ngn !== null && Number.isFinite(fee))
  const feeSummary = fees.length
    ? fees.length === 1 || Math.min(...fees) === Math.max(...fees)
      ? formatNgn(Math.min(...fees))
      : `${formatNgn(Math.min(...fees))}–${formatNgn(Math.max(...fees))}`
    : 'Not configured'
  const venue = options?.venue || 'To be announced'

  return <aside className="dic-info-card"><div className="dic-card-top"><span>{canRegister ? 'Registration Open' : 'Registration Information'}</span><small>Portal Status</small></div><h2>{options?.name || 'Camp Information'}</h2><dl><dt>Camp dates</dt><dd>{options ? `${formatDate(options.camp_start_date)} – ${formatDate(options.camp_end_date)}` : 'To be announced'}</dd><dt>Venue</dt><dd>{venue}</dd>{options?.venue_directions_url && <><dt>Directions</dt><dd><a href={options.venue_directions_url} target="_blank" rel="noopener noreferrer">Open Google Maps directions ↗</a></dd></>}{options?.registration_open_date && <><dt>Registration</dt><dd>{formatDate(options.registration_open_date)} – {formatDate(options.registration_close_date)}</dd></>}<dt>Current fees</dt><dd>{feeSummary}</dd></dl>{categories.length > 0 && <div className="dic-price-list">{categories.map((category) => <p key={category.id}><strong>{category.name}</strong><br />Early bird: {category.early_bird_fee_ngn === null ? 'Not configured' : formatNgn(category.early_bird_fee_ngn)} · Regular: {category.regular_fee_ngn === null ? 'Not configured' : formatNgn(category.regular_fee_ngn)}<br />Current price: {category.current_fee_ngn === null ? 'Not configured' : formatNgn(category.current_fee_ngn)}</p>)}</div>}{options?.early_bird_cutoff_at_lagos && <small>Early-bird payment deadline: {formatLagosDateTime(options.early_bird_cutoff_at_lagos)} (Africa/Lagos). The discount applies only when payment is completed before this time.</small>}{optionsState === 'error' ? <button className="button button-outline" type="button" onClick={onRetry}>Retry loading details</button> : <button className="button" type="button" onClick={onRegister} disabled={!canRegister}>Register for DIC <span aria-hidden="true">→</span></button>}<small>{status}</small><Link className="dic-recovery-link" to="/dic/register/recover">Already registered? Recover your registration</Link></aside>
}

function DICLanding({ options, optionsState, onRegister, onRetry }) {
  return <div className="dic-page"><section className="dic-hero"><Container><div className="dic-hero-grid"><div className="dic-hero-copy"><span className="eyebrow">DARUL ISLAM CAMP · DIC</span><h1>Darul Islam Camp</h1><p className="dic-hero-lead">A major initiative of Da&apos;wãnã Islamic Foundation.</p><p>Darul Islam Camp is a platform for intensive Islamic learning, spiritual development, youth engagement, intellectual reflection, community interaction, and personal and social development.</p><span className="dic-hero-meta">✦ &nbsp; Learning · Reflection · Community</span></div><DICInfoPanel options={options} optionsState={optionsState} onRegister={onRegister} onRetry={onRetry} /></div></Container></section><section className="dic-about"><Container><span className="eyebrow">A Foundation initiative</span><h2>Learning, reflection and growth</h2><p>Darul Islam Camp brings participants together for focused Islamic learning, spiritual development, youth engagement and community interaction. It supports personal and social development through a shared space for learning and reflection.</p></Container></section><section className="dic-areas"><Container><span className="eyebrow">Camp focus</span><h2>A space to learn and develop</h2><div className="dic-area-grid">{[['01', 'Intensive Islamic learning', 'A focused platform for learning and engagement with Islamic knowledge.'], ['02', 'Spiritual development', 'Space for reflection and continued personal development.'], ['03', 'Youth engagement', 'Encouraging meaningful participation and connection among young people.'], ['04', 'Community interaction', 'Building connection through shared learning and interaction.']].map(([number, title, copy]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{copy}</p></article>)}</div></Container></section><section className="dic-process"><Container><div className="dic-register-bar"><div><strong>Darul Islam Camp registration</strong><span>{options ? `${formatDate(options.camp_start_date)} – ${formatDate(options.camp_end_date)} · ${options.registration_is_open ? 'Registration open' : 'Registration closed'}` : 'Registration information is not currently available.'}</span></div><button className="button" type="button" onClick={onRegister} disabled={optionsState !== 'ready' || !options?.registration_is_open || !options.categories?.length}>Register for DIC <span aria-hidden="true">→</span></button></div>{optionsState === 'error' && <FlowMessage kind="error">Registration information could not be loaded. Please try again later.</FlowMessage>}{optionsState === 'ready' && (!options.registration_is_open || !options.categories.length) && <FlowMessage>{options.registration_is_open ? 'No registration categories are currently available.' : 'Registration is not currently open.'}</FlowMessage>}</Container></section></div>
}

function ParticipantForm({ initial, categories, options, onBack, onSave, isEditing }) {
  const [participant, setParticipant] = useState(() => ({ ...emptyParticipant, ...initial }))
  const update = (event) => setParticipant((current) => ({ ...current, [event.target.name]: event.target.value }))
  const submit = (event) => { event.preventDefault(); onSave(participant) }
  const today = localDateInputValue()
  return <section className="dic-flow"><Container><p className="dic-breadcrumb"><Link to="/">Home</Link> &nbsp;›&nbsp; <Link to="/dic">DIC</Link> &nbsp;›&nbsp; Registration</p><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · DIC REGISTRATION</span><h1>{isEditing ? 'Edit participant' : 'Participant registration'}</h1><p>{options?.name}: {formatDate(options?.camp_start_date)} – {formatDate(options?.camp_end_date)} · Venue: {options?.venue || 'To be announced'}</p><p>Each participant has an individual registration. Multiple registrations can be grouped at checkout.</p></div><aside className="dic-flow-note">Select an edition category for each participant. The server confirms the final fee when your order is created.</aside></div>{options?.early_bird_cutoff_at_lagos && <FlowMessage>Early-bird price applies only when payment is successfully completed before {formatLagosDateTime(options.early_bird_cutoff_at_lagos)} (Africa/Lagos).</FlowMessage>}<RegistrationProgress current="form" /><form className="dic-form" onSubmit={submit}><h2>Participant information</h2><p>Complete the required details for this participant.</p><h3>Personal information</h3><div className="dic-form-grid"><Field label="Full Name" name="fullName" value={participant.fullName} onChange={update} wide placeholder="Enter full name" /><Field label="Address" name="address" value={participant.address} onChange={update} wide placeholder="Enter address" /><Field label="Phone" name="phone" value={participant.phone} onChange={update} type="tel" placeholder="Phone number" /><Field label="Email" name="email" value={participant.email} onChange={update} type="email" placeholder="name@example.com" /><Field label="Date of Birth" name="dob" value={participant.dob} onChange={update} type="date" max={today} /><fieldset className="dic-field dic-radio-field"><legend>Sex <b>*</b></legend><div>{['Male', 'Female'].map((sex) => <label key={sex}><input type="radio" name="sex" value={sex} checked={participant.sex === sex} onChange={update} required />{sex}</label>)}</div></fieldset><h3 className="dic-form-section-title">Measurements</h3><Field label="Height" name="height" value={participant.height} onChange={update} type="number" min="0.01" step="0.01" placeholder="e.g. 175" unit="cm" /><Field label="Weight" name="weight" value={participant.weight} onChange={update} type="number" min="0.01" step="0.01" placeholder="e.g. 70" unit="kg" /><h3 className="dic-form-section-title">Background</h3><Field label="Academic Status" name="academicStatus" value={participant.academicStatus} onChange={update} options={academicOptions} /><Field label="Occupation" name="occupation" value={participant.occupation} onChange={update} options={occupations} /><Field label="Marital Status" name="maritalStatus" value={participant.maritalStatus} onChange={update} options={maritalOptions} /><CategorySelection categories={categories} value={participant.categoryId} onChange={update} earlyBirdCutoff={options?.early_bird_cutoff_at} /></div><div className="dic-form-actions"><button className="text-link" type="button" onClick={onBack}>← Back</button><button className="button" type="submit">{isEditing ? 'Save changes' : 'Continue to summary'} <span aria-hidden="true">→</span></button></div></form></Container></section>
}

function ParticipantCard({ participant, index, category, fee, priceType, onEdit, onRemove, locked }) {
  return <article className="participant-card"><div className="participant-card-copy"><span className="participant-number">Participant {index + 1}</span><h3>{participant.fullName}</h3><span className="status-pill">{participant.academicStatus}</span><p>{participant.email} · {participant.phone}</p><p>Category: <strong>{category?.name || 'Unavailable category'}</strong></p><p>Registration fee: <strong>{fee === null ? 'Not available' : formatNgn(fee)}{priceType ? ` · ${priceType === 'early_bird' ? 'Early bird' : 'Regular'}` : ''}</strong></p></div>{!locked && <div className="participant-actions"><button type="button" onClick={onEdit}>Edit</button><button className="remove" type="button" onClick={onRemove}>Remove</button></div>}</article>
}

function RegistrationSummary({ flow, categories, onAdd, onEdit, onRemove, onCheckout, options }) {
  const locked = Boolean(flow.orderId || flow.submissionUncertain)
  const serverItems = flow.orderSummary?.items || []
  const total = flow.orderSummary
    ? flow.orderSummary.total_amount_ngn
    : flow.participants.reduce((sum, participant) => {
      const category = categories.find((item) => String(item.id) === String(participant.categoryId))
      return sum + (category && category.current_fee_ngn !== null ? Number(category.current_fee_ngn) : 0)
    }, 0)
  return <section className="dic-summary"><Container><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · DIC</span><h1>Registration summary</h1><p>{formatDate(options?.camp_start_date)} – {formatDate(options?.camp_end_date)} · Venue: {options?.venue || 'To be announced'}</p><p>Review each participant before continuing to checkout.</p></div></div>{options?.early_bird_cutoff_at_lagos && <FlowMessage>Early-bird price is secured only when payment completes before {formatLagosDateTime(options.early_bird_cutoff_at_lagos)} (Africa/Lagos).</FlowMessage>}<RegistrationProgress current="summary" /><FlowMessage kind={locked ? 'info' : 'error'}>{locked ? 'The submitted order is locked to protect its accepted price history. Continue to checkout to resume payment.' : null}</FlowMessage><div className="dic-add-note"><span>Each participant is registered individually. You can group registrations in one checkout.</span>{!locked && <button className="button button-small" type="button" onClick={onAdd}>+ Add participant</button>}</div><div className="dic-summary-layout"><div><div className="dic-summary-heading"><h2>Registered participants</h2><span>{flow.participants.length} {flow.participants.length === 1 ? 'participant' : 'participants'}</span></div>{flow.participants.map((participant, index) => { const category = categories.find((item) => String(item.id) === String(participant.categoryId)); const item = serverItems[index]; const fee = item ? item.fee_ngn : category?.current_fee_ngn ?? null; return <ParticipantCard key={participant.id} participant={participant} index={index} category={item ? { name: item.category_name } : category} fee={fee} priceType={item?.price_type} locked={locked} onEdit={() => onEdit(index)} onRemove={() => onRemove(index)} /> })}</div><aside className="summary-box"><h2>Registration summary</h2><p>{options?.name || 'Darul Islam Camp'}</p><hr /><div className="dic-summary-line"><span>Participants</span><strong>{flow.participants.length}</strong></div><div className="dic-summary-line"><span>{flow.orderSummary ? 'Server-calculated total' : 'Estimated total'}</span><strong>{formatNgn(total)}</strong></div><small>{flow.orderSummary ? 'This total reflects the accepted server price revision.' : 'The final fee is calculated by the registration service when you create your order.'}</small><button className="button" type="button" onClick={onCheckout}>Continue to checkout →</button>{!locked && <button className="button button-outline" type="button" onClick={onAdd}>+ Add another participant</button>}</aside></div></Container></section>
}

function CheckoutSummary({ flow, categories, options }) {
  const items = flow.orderSummary?.items || []
  return <div className="checkout-summary"><h2>Registration summary</h2><p>{options?.name || 'Darul Islam Camp'} · {formatDate(options?.camp_start_date)} – {formatDate(options?.camp_end_date)} · {options?.venue || 'Venue to be announced'}</p>{flow.participants.map((participant, index) => { const category = categories.find((item) => String(item.id) === String(participant.categoryId)); const item = items[index]; const fee = item?.fee_ngn ?? category?.current_fee_ngn; return <div className="checkout-row" key={participant.id}><span>{participant.fullName}<small>{item?.category_name || category?.name || 'Category unavailable'}{item?.price_type ? ` · ${item.price_type === 'early_bird' ? 'Early-bird price' : 'Regular price'}` : ''}</small></span><strong>{fee === undefined || fee === null ? '—' : formatNgn(fee)}</strong></div>})}<div className="checkout-row checkout-total"><span>{flow.orderSummary ? 'Server-calculated total' : 'Current estimated total'}</span><strong>{formatNgn(flow.orderSummary?.total_amount_ngn ?? flow.participants.reduce((sum, participant) => { const category = categories.find((item) => String(item.id) === String(participant.categoryId)); return sum + (category && category.current_fee_ngn !== null ? Number(category.current_fee_ngn) : 0) }, 0))}</strong></div>{options?.early_bird_cutoff_at_lagos && <small>Early-bird fee is secured only by payment completed before {formatLagosDateTime(options.early_bird_cutoff_at_lagos)} (Africa/Lagos).</small>}</div>
}

function Checkout({ flow, categories, options, accessToken, busy, error, paymentNotice, repricingOffer, onAcceptRepricing, onBack, onCreateOrder, onResume, onInitialize, onVerify, onCheckoutClosed }) {
  const requiresRecovery = Boolean(flow.orderId && !accessToken)
  const needsOrder = !flow.orderId
  const canVerify = Boolean(accessToken && flow.paymentReference)
  const retryingOrder = needsOrder && flow.submissionUncertain
  return <section className="dic-summary"><Container><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · REGISTRATION</span><h1>Checkout</h1><p>Review your grouped registration.</p></div></div><RegistrationProgress current="checkout" /><div className="checkout-box"><CheckoutSummary flow={flow} categories={categories} options={options} /><FlowMessage kind="error">{error}</FlowMessage><FlowMessage kind={paymentNotice?.kind || 'info'}>{paymentNotice?.text}</FlowMessage>{repricingOffer && <div className="payment-placeholder" role="alert"><strong>Updated amount requires your approval</strong><p>Your early-bird quote expired before payment was completed. The registration and participant details are preserved. An earlier Paystack authorization may still be active; do not use its old checkout link. A payment will be accepted only if Paystack confirms its amount and completion time.</p>{repricingOffer.items.map((item, index) => <p key={`${item.category_name}-${index}`}>{item.category_name} — {item.price_type === 'early_bird' ? 'Early bird' : 'Regular'}: {formatNgn(item.fee_ngn)}</p>)}<p><strong>Revised total: {formatNgn(repricingOffer.total_amount_ngn)}</strong></p><button className="button" type="button" onClick={onAcceptRepricing} disabled={busy}>{busy ? 'Updating secure quote…' : 'Accept revised amount and continue'}</button></div>}{needsOrder && <div className="payment-placeholder"><strong>{retryingOrder ? 'Retry secure order submission' : 'Secure order creation'}</strong><p>{retryingOrder ? 'The previous request may have completed without a response. Retrying with the same idempotency key prevents creating a duplicate order.' : 'Your registration will be submitted to the Dawana registration service. The order total returned by the server is authoritative.'}</p></div>}{requiresRecovery && <div className="payment-placeholder"><strong>Secure checkout needs to be restored</strong><p>Your bearer token is never saved in browser storage. Restore this short-lived session to obtain a fresh token and resume payment. If your payment was completed, it will be checked before any new payment is offered.</p></div>}{flow.orderId && accessToken && <div className="payment-placeholder"><strong>{flow.paymentStatus === 'paid' ? 'Payment verified' : 'Paystack test-mode checkout'}</strong><p>{flow.paymentStatus === 'paid' ? 'The registration service has confirmed this payment.' : 'Checkout opens in a separate tab so this page can securely verify your payment when you return. A redirect alone never confirms payment.'}</p>{flow.paymentReference && <span>Payment reference: {flow.paymentReference}</span>}{flow.authorizationUrl && !repricingOffer && <><a className="button button-outline dic-checkout-link" href={flow.authorizationUrl} target="_blank" rel="noopener noreferrer">Open Paystack checkout in a new tab ↗</a><button className="text-link dic-checkout-closed" type="button" onClick={onCheckoutClosed}>I cancelled or closed checkout</button></>}</div>}<div className="dic-form-actions"><button className="text-link" type="button" onClick={onBack} disabled={busy}>← Back to summary</button>{needsOrder ? <button className="button" type="button" onClick={onCreateOrder} disabled={busy}>{busy ? 'Submitting secure order…' : retryingOrder ? 'Retry order submission safely →' : 'Create order and continue to payment →'}</button> : requiresRecovery ? <button className="button" type="button" onClick={onResume} disabled={busy}>{busy ? 'Restoring secure session…' : 'Restore secure checkout →'}</button> : flow.paymentStatus === 'paid' ? <button className="button" type="button" disabled>Payment confirmed</button> : repricingOffer ? null : canVerify ? <div className="dic-payment-actions">{flow.paymentStatus === 'failed' && <button className="button button-outline" type="button" onClick={onInitialize} disabled={busy}>{busy ? 'Starting…' : 'Try payment again'}</button>}<button className="button" type="button" onClick={onVerify} disabled={busy}>{busy ? 'Verifying with Paystack…' : 'I have returned — verify payment'}</button></div> : <button className="button" type="button" onClick={onInitialize} disabled={busy}>{busy ? 'Connecting to Paystack…' : 'Prepare Paystack checkout →'}</button>}</div></div></Container></section>
}

function Confirmation({ flow, onReset }) {
  const paid = flow.paymentStatus === 'paid'
  return <section className="dic-summary"><Container><RegistrationProgress current="confirmation" /><div className="confirmation-box"><span className="confirmation-icon" aria-hidden="true">{paid ? '✓' : '!'}</span><span className="eyebrow">{paid ? 'PAYMENT VERIFIED' : 'PAYMENT NOT VERIFIED'}</span><h1>{paid ? 'DIC registration confirmed' : 'Registration awaiting payment verification'}</h1><p>{paid ? `Your ${flow.participants.length === 1 ? 'participant registration has' : `${flow.participants.length} participant registrations have`} been confirmed by the registration service.` : 'A successful redirect is not proof of payment. Return to checkout and verify the payment with the registration service before treating this registration as complete.'}</p>{flow.orderId && <strong>Order reference: {flow.orderId}</strong>}{paid && <button className="button" type="button" onClick={onReset}>Return to DIC</button>}</div></Container></section>
}

function RecoveryPage() {
  const [channels, setChannels] = useState(null)
  const [channel, setChannel] = useState('email')
  const [contact, setContact] = useState('')
  const [code, setCode] = useState('')
  const [challengeId, setChallengeId] = useState(null)
  const [recoveryGrant, setRecoveryGrant] = useState(null)
  const [orders, setOrders] = useState([])
  const [selectedOrder, setSelectedOrder] = useState(null)
  const [restoredOrder, setRestoredOrder] = useState(null)
  const [paymentAttempt, setPaymentAttempt] = useState(null)
  const [repricingOffer, setRepricingOffer] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resendSeconds, setResendSeconds] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    getRecoveryChannels()
      .then((result) => { if (active) setChannels(result) })
      .catch((loadError) => { if (active) setError(getErrorMessage(loadError, 'Recovery information is unavailable.')) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (resendSeconds <= 0) return undefined
    const timer = window.setTimeout(() => setResendSeconds((seconds) => Math.max(0, seconds - 1)), 1000)
    return () => window.clearTimeout(timer)
  }, [resendSeconds])

  const selectedChannel = channels?.channels.find((item) => item.id === channel)
  const recoveryError = (requestError) => {
    if (requestError.statusCode === 429) return 'Please wait before requesting another code or trying again.'
    if (requestError.statusCode === 503) return 'This recovery channel is not available right now.'
    return getErrorMessage(requestError, 'The recovery request could not be completed. Please try again.')
  }

  const startRecovery = async (event) => {
    event.preventDefault()
    if (busy || !selectedChannel?.available) return
    setBusy(true)
    setError('')
    setMessage('')
    setPaymentAttempt(null)
    try {
      const result = await requestRecoveryCode(channel, contact)
      setChallengeId(result.challenge_id)
      setResendSeconds(result.resend_after)
      setMessage(result.message)
      setCode('')
    } catch (requestError) {
      setError(recoveryError(requestError))
    } finally {
      setBusy(false)
    }
  }

  const verifyCode = async (event) => {
    event.preventDefault()
    if (busy || !challengeId) return
    setBusy(true)
    setError('')
    try {
      const verification = await verifyRecoveryCode(challengeId, code)
      const result = await getRecoveryOrders(verification.recovery_grant)
      setRecoveryGrant(verification.recovery_grant)
      setOrders(result.orders)
      setCode('')
      setMessage(result.orders.length
        ? 'Choose the registration you want to recover.'
        : 'No recoverable registrations were found for the verified contact.')
    } catch (requestError) {
      setError(requestError.statusCode === 429
        ? 'Too many attempts. Request a new code later.'
        : 'That code could not be verified. Check it and try again, or request a new code.')
    } finally {
      setBusy(false)
    }
  }

  const resendCode = async () => {
    if (busy || resendSeconds > 0 || !challengeId) return
    setBusy(true)
    setError('')
    try {
      const result = await resendRecoveryCode(challengeId, channel, contact)
      setResendSeconds(result.resend_after)
      setMessage(result.message)
      setCode('')
    } catch (requestError) {
      setError(recoveryError(requestError))
    } finally {
      setBusy(false)
    }
  }

  const restoreOrder = async (order) => {
    if (busy || !recoveryGrant) return
    setBusy(true)
    setError('')
    setPaymentAttempt(null)
    setRepricingOffer(null)
    try {
      const result = await restoreRecoveredOrder(order.order_id, recoveryGrant)
      setSelectedOrder(order)
      setRestoredOrder({ ...result.order, accessToken: result.access_token })
      setMessage('')
    } catch (requestError) {
      setError(requestError.statusCode === 404
        ? 'This recovery session expired or the order is no longer available. Start recovery again.'
        : recoveryError(requestError))
    } finally {
      setBusy(false)
    }
  }

  const preparePayment = async () => {
    if (busy || !restoredOrder || restoredOrder.payment_status === 'paid') return
    setBusy(true)
    setError('')
    setMessage('')
    setPaymentAttempt(null)
    try {
      const result = await initializePayment(
        restoredOrder.order_id,
        restoredOrder.accessToken,
      )
      setPaymentAttempt(result)
      setMessage(result.authorization_url
        ? 'Checkout is ready. Complete payment, return here, and verify it with the registration service.'
        : 'No checkout link was returned. Payment has not been confirmed.')
    } catch (requestError) {
      if (requestError.body?.repricing_required && requestError.body?.quote) {
        setRepricingOffer(requestError.body)
        setMessage('The saved early-bird quote expired. Review and accept the updated amount before paying.')
      } else {
        setError(requestError.statusCode === 503
          ? 'Online payment is not configured right now. Your registration remains safely recorded as unpaid.'
          : recoveryError(requestError))
      }
    } finally {
      setBusy(false)
    }
  }

  const acceptRecoveredRepricing = async () => {
    if (busy || !restoredOrder || !repricingOffer) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const accepted = await acceptOrderPricing(
        restoredOrder.order_id,
        repricingOffer.quote,
        restoredOrder.accessToken,
      )
      if (accepted.repricing_required) {
        setRepricingOffer(accepted)
        setMessage('The current amount changed again. Review the latest quote before accepting.')
        return
      }
      const updatedOrder = {
        ...restoredOrder,
        total_amount_ngn: accepted.total_amount_ngn,
        items: repricingOffer.items.map((item) => ({
          category_name: item.category_name,
          fee_ngn: item.fee_ngn,
          price_type: item.price_type,
        })),
      }
      setRestoredOrder(updatedOrder)
      setRepricingOffer(null)
      const attempt = await initializePayment(
        updatedOrder.order_id,
        updatedOrder.accessToken,
      )
      setPaymentAttempt(attempt)
      setMessage(attempt.authorization_url
        ? 'The revised amount was accepted and the new checkout is ready.'
        : 'The revised amount was accepted, but no checkout link is available. Payment is not confirmed.')
    } catch (requestError) {
      if (requestError.body?.repricing_required && requestError.body?.quote) {
        setRepricingOffer(requestError.body)
        setMessage('The current amount changed again. Review the latest quote before accepting.')
      } else {
        setError(recoveryError(requestError))
      }
    } finally {
      setBusy(false)
    }
  }

  const verifyRecoveredPayment = async () => {
    if (busy || !restoredOrder || !paymentAttempt?.payment_reference) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await verifyPayment(
        restoredOrder.order_id,
        paymentAttempt.payment_reference,
        restoredOrder.accessToken,
      )
      setRestoredOrder((current) => ({
        ...current,
        payment_status: result.payment_status,
        status: result.payment_status === 'paid' ? 'confirmed' : current.status,
      }))
      setMessage(result.payment_status === 'paid'
        ? 'Payment was verified by the registration service.'
        : ['reconcile', 'amount_mismatch'].includes(result.attempt_status)
          ? 'The provider reports a charge that needs administrator reconciliation. The registration is not confirmed; do not retry payment until it has been reviewed.'
        : 'Payment has not been verified as successful. Your registration remains unconfirmed.')
    } catch (requestError) {
      setError(requestError.statusCode === 404
        ? 'This order or payment attempt is no longer available. Recover the order again to continue.'
        : 'Payment status could not be verified. No successful registration is assumed.')
    } finally {
      setBusy(false)
    }
  }

  const restart = () => {
    setChallengeId(null)
    setRecoveryGrant(null)
    setOrders([])
    setSelectedOrder(null)
    setRestoredOrder(null)
    setPaymentAttempt(null)
    setRepricingOffer(null)
    setCode('')
    setError('')
    setMessage('')
  }

  return <section className="dic-flow dic-recovery-page"><Container><p className="dic-breadcrumb"><Link to="/dic">DIC</Link> &nbsp;›&nbsp; Registration recovery</p><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · SECURE ACCESS</span><h1>Recover your registration</h1><p>Verify a contact method already associated with your registration to retrieve its current status.</p></div><aside className="dic-flow-note">Recovery does not create a new registration or confirm a payment.</aside></div><div className="dic-recovery-card"><FlowMessage kind="error">{error}</FlowMessage><FlowMessage>{message}</FlowMessage>{loading ? <p role="status">Loading available recovery methods…</p> : !channels ? <p>Recovery information could not be loaded. Please try again later.</p> : restoredOrder ? <div className="dic-recovery-order"><span className="eyebrow">{restoredOrder.payment_status === 'paid' ? 'PAYMENT VERIFIED' : 'REGISTRATION RECOVERED'}</span><h2>{restoredOrder.payment_status === 'paid' ? 'Registration confirmed' : 'Registration status'}</h2><p><strong>Order reference:</strong> {restoredOrder.order_id}</p><p><strong>Camp:</strong> {restoredOrder.edition_name}</p><p><strong>Participants:</strong> {restoredOrder.participant_count}</p><p><strong>Total:</strong> {formatNgn(restoredOrder.total_amount_ngn)}</p><p><strong>Payment:</strong> {restoredOrder.payment_status}</p>{restoredOrder.items.map((item, index) => <p key={`${item.category_name}-${index}`}>{item.category_name} — {formatNgn(item.fee_ngn)}{item.price_type ? ` · ${item.price_type === 'early_bird' ? 'Early bird' : 'Regular'}` : ''}</p>)}{repricingOffer && <div className="payment-placeholder" role="alert"><strong>Updated amount needs your approval</strong><p>The saved early-bird quote expired. Your registration remains saved. Do not reuse an earlier payment authorization; provider-confirmed completion time and amount will be checked.</p>{repricingOffer.items.map((item, index) => <p key={`${item.category_name}-${index}`}>{item.category_name} — {item.price_type === 'early_bird' ? 'Early bird' : 'Regular'}: {formatNgn(item.fee_ngn)}</p>)}<p><strong>Revised total: {formatNgn(repricingOffer.total_amount_ngn)}</strong></p><button className="button" type="button" onClick={acceptRecoveredRepricing} disabled={busy}>{busy ? 'Updating secure quote…' : 'Accept revised amount and continue'}</button></div>}{restoredOrder.payment_status === 'refunded' && <p role="status">This registration was refunded and cannot be paid again through this checkout.</p>}{!['paid', 'refunded'].includes(restoredOrder.payment_status) && !repricingOffer && <><button className="button" type="button" onClick={preparePayment} disabled={busy}>{busy ? 'Preparing secure checkout…' : 'Continue to payment →'}</button>{paymentAttempt?.authorization_url && <a className="button button-outline dic-checkout-link" href={paymentAttempt.authorization_url} target="_blank" rel="noopener noreferrer">Open secure payment checkout ↗</a>}{paymentAttempt?.payment_reference && <button className="button button-outline" type="button" onClick={verifyRecoveredPayment} disabled={busy}>{busy ? 'Verifying payment…' : 'Verify payment status'}</button>}</>}<button className="text-link" type="button" onClick={() => { setRestoredOrder(null); setPaymentAttempt(null); setRepricingOffer(null); setSelectedOrder(null) }}>Choose another registration</button></div> : selectedOrder ? <div className="dic-recovery-order"><h2>Registration selected</h2><p>{selectedOrder.edition_name} · {selectedOrder.participant_count} {selectedOrder.participant_count === 1 ? 'participant' : 'participants'}</p><p>{formatNgn(selectedOrder.total_amount_ngn)} · Payment {selectedOrder.payment_status}</p><button className="button" type="button" onClick={() => restoreOrder(selectedOrder)} disabled={busy}>{busy ? 'Restoring secure access…' : 'Restore this registration →'}</button><button className="text-link" type="button" onClick={() => setSelectedOrder(null)}>Choose another registration</button></div> : orders.length ? <div className="dic-recovery-orders"><h2>Your registrations</h2>{orders.map((order) => <article key={order.order_id}><div><strong>{order.edition_name}</strong><span>{order.participant_count} {order.participant_count === 1 ? 'participant' : 'participants'} · {formatNgn(order.total_amount_ngn)}</span><small>Payment {order.payment_status}</small></div><button className="button button-outline" type="button" onClick={() => setSelectedOrder(order)}>Select</button></article>)}</div> : challengeId ? <form className="dic-recovery-form" onSubmit={verifyCode}><h2>Enter your verification code</h2><p>Enter the six-digit code if one was sent. Codes expire after 10 minutes. Do not share a code with anyone.</p><label className="dic-field" htmlFor="recovery-code"><span>Verification code</span><input id="recovery-code" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} required /></label><div className="dic-form-actions"><button className="button" type="submit" disabled={busy || code.length !== 6}>{busy ? 'Verifying…' : 'Verify code'}</button><button className="text-link" type="button" disabled={busy || resendSeconds > 0} onClick={resendCode}>{resendSeconds > 0 ? `Resend available in ${resendSeconds}s` : 'Resend code'}</button><button className="text-link" type="button" onClick={restart}>Start over</button></div></form> : <><form className="dic-recovery-form" onSubmit={startRecovery}><h2>Verify your contact</h2><p>Use an email address or phone number already included in the registration.</p><RegistrationSelect id="recovery-channel" label="Verification method" value={channel} onChange={(event) => setChannel(event.target.value)} options={channels.channels.map((item) => ({ value: item.id, label: `${item.label}${item.available ? '' : ' - unavailable'}`, disabled: !item.available }))} />{selectedChannel?.available && <label className="dic-field" htmlFor="recovery-contact"><span>{channel === 'email' ? 'Email address' : 'Phone number'}</span><input id="recovery-contact" name="contact" type={channel === 'email' ? 'email' : 'tel'} autoComplete={channel === 'email' ? 'email' : 'tel'} inputMode={channel === 'email' ? undefined : 'tel'} value={contact} onChange={(event) => setContact(event.target.value)} required /></label>}<button className="button" type="submit" disabled={busy || !selectedChannel?.available}>{busy ? 'Sending request…' : 'Send verification code'}</button>{!channels.channels.some((item) => item.available) && <FlowMessage kind="error">Automated recovery is not configured yet. Contact the DIC registration team for assistance.</FlowMessage>}</form>{channels.whatsapp_support_url && <p className="dic-recovery-support">Need help? <a href={channels.whatsapp_support_url} target="_blank" rel="noopener noreferrer">Contact DIC support on WhatsApp</a>. A conversation does not verify registration ownership.</p>}</>}</div><p className="dic-recovery-back"><Link to="/dic">← Return to DIC</Link></p></Container></section>
}

function getStep(pathname) {
  if (pathname.endsWith('/recover')) return 'recovery'
  if (pathname.endsWith('/confirmation')) return 'confirmation'
  if (pathname.endsWith('/checkout')) return 'checkout'
  if (pathname.endsWith('/summary')) return 'summary'
  if (pathname.startsWith('/dic/register')) return 'form'
  return 'landing'
}

export default function DIC() {
  const location = useLocation()
  const navigate = useNavigate()
  const step = getStep(location.pathname)
  const [loadedFlow] = useState(loadFlow)
  const [flow, setFlow] = useState(loadedFlow.flow)
  const [accessToken, setAccessToken] = useState(null)
  const [options, setOptions] = useState(null)
  const [optionsState, setOptionsState] = useState('loading')
  const [optionsError, setOptionsError] = useState('')
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(loadedFlow.expired ? 'Your saved registration session expired. Please review and enter your registration again.' : '')
  const [paymentNotice, setPaymentNotice] = useState(
    loadedFlow.storageAvailable ? null : { kind: 'error', text: 'This browser could not retain a temporary recovery draft. Keep this tab open until payment is verified.' },
  )
  const [repricingOffer, setRepricingOffer] = useState(null)

  const persistFlow = useCallback((nextFlow) => {
    const saved = { ...nextFlow, expiresAt: Date.now() + DRAFT_LIFETIME_MS }
    setFlow(saved)
    if (!saveFlow(saved)) {
      setPaymentNotice({
        kind: 'error',
        text: 'The temporary recovery draft could not be saved. Keep this tab open until payment is verified.',
      })
    }
  }, [])

  const receiveOptions = useCallback((data) => {
    setOptions(data)
    setOptionsState('ready')
    setOptionsError('')
  }, [])
  const rejectOptions = useCallback((loadError) => {
    setOptions(null)
    setOptionsState(loadError.statusCode === 404 ? 'none' : 'error')
    setOptionsError(loadError.statusCode === 404 ? 'No active DIC edition is currently configured.' : getErrorMessage(loadError, 'Registration information is unavailable.'))
  }, [])
  const loadOptions = () => getRegistrationOptions().then(receiveOptions).catch(rejectOptions)

  useEffect(() => {
    let active = true
    getRegistrationOptions()
      .then((data) => { if (active) receiveOptions(data) })
      .catch((loadError) => { if (active) rejectOptions(loadError) })
    return () => { active = false }
  }, [receiveOptions, rejectOptions])

  const retryOptions = () => {
    setOptionsState('loading')
    setOptionsError('')
    loadOptions()
  }

  const go = (next) => navigate(routeFor[next])
  const updateParticipants = (participants, resetOrder = false) => {
    const nextFlow = {
      ...flow,
      participants,
      ...(resetOrder ? {
        idempotencyKey: newUuidV4(),
        orderId: null,
        orderSummary: null,
        paymentReference: null,
        paymentStatus: 'pending',
        submissionUncertain: false,
      } : {}),
    }
    persistFlow(nextFlow)
  }
  const saveParticipant = (participant) => {
    const participants = editing === null
      ? [...flow.participants, { ...participant, id: newUuidV4() }]
      : flow.participants.map((item, index) => index === editing ? { ...participant, id: item.id } : item)
    updateParticipants(participants, true)
    setEditing(null)
    go('summary')
  }
  const add = () => { setEditing(null); go('form') }
  const edit = (index) => { setEditing(index); go('form') }
  const reset = () => {
    clearSavedFlow()
    setAccessToken(null)
    setError('')
    setPaymentNotice(null)
    setRepricingOffer(null)
    const fresh = emptyFlow()
    setFlow(fresh)
    saveFlow(fresh)
    setEditing(null)
    go('landing')
  }

  const initializeForOrder = async (orderId, token, orderSummary = flow.orderSummary) => {
    try {
      const attempt = await initializePayment(orderId, token)
      const nextFlow = {
        ...flow,
        orderId,
        orderSummary,
        paymentReference: attempt.payment_reference,
        paymentStatus: attempt.payment_status,
        authorizationUrl: attempt.authorization_url,
        submissionUncertain: false,
      }
      persistFlow(nextFlow)
      setError('')
      setPaymentNotice(attempt.authorization_url
        ? { kind: 'info', text: 'Your secure Paystack checkout is ready. Open it in a new tab, then return here to verify payment.' }
        : { kind: 'error', text: 'Paystack is not currently available. Your order is safely recorded; you may retry when test-mode credentials are configured.' })
    } catch (paymentError) {
      if (paymentError.body?.repricing_required && paymentError.body?.quote) {
        const nextFlow = {
          ...flow,
          orderId,
          orderSummary,
          authorizationUrl: null,
          submissionUncertain: false,
        }
        persistFlow(nextFlow)
        setRepricingOffer(paymentError.body)
        setError('')
        setPaymentNotice({
          kind: 'info',
          text: 'The early-bird quote expired before payment was completed. Review and explicitly accept the updated amount to continue.',
        })
        return
      }
      const reference = paymentReferenceFromError(paymentError)
      if (reference) {
        const nextFlow = { ...flow, orderId, orderSummary, paymentReference: reference, authorizationUrl: null, submissionUncertain: false }
        persistFlow(nextFlow)
      }
      setError('')
      setPaymentNotice({
        kind: 'error',
        text: paymentError.statusCode === 503
          ? 'Online payment is not available right now. Your order is recorded, but payment has not been made.'
          : reference
            ? 'The payment attempt needs verification before it can be retried. Use the verification button below.'
            : getErrorMessage(paymentError, 'A payment attempt could not be started. Your order has not been marked paid.'),
      })
    }
  }

  const acceptRepricing = async () => {
    if (busy || !repricingOffer || !flow.orderId || !accessToken) return
    setBusy(true)
    setError('')
    setPaymentNotice(null)
    try {
      const result = await acceptOrderPricing(
        flow.orderId,
        repricingOffer.quote,
        accessToken,
      )
      if (result.repricing_required) {
        setRepricingOffer(result)
        setPaymentNotice({
          kind: 'info',
          text: 'The price changed again. Review the latest amount and accept it to continue.',
        })
        return
      }
      setRepricingOffer(null)
      const orderSummary = {
        ...flow.orderSummary,
        total_amount_ngn: result.total_amount_ngn,
        items: repricingOffer.items.map((item) => ({
          category_name: item.category_name,
          fee_ngn: item.fee_ngn,
          price_type: item.price_type,
        })),
      }
      persistFlow({
        ...flow,
        orderSummary,
        paymentReference: null,
        authorizationUrl: null,
      })
      await initializeForOrder(flow.orderId, accessToken, orderSummary)
    } catch (pricingError) {
      if (pricingError.body?.repricing_required && pricingError.body?.quote) {
        setRepricingOffer(pricingError.body)
        setPaymentNotice({
          kind: 'info',
          text: 'The amount changed again. Review the latest quote and confirm it before continuing.',
        })
      } else {
        setError(getErrorMessage(pricingError, 'The revised price could not be accepted. No new payment was started.'))
      }
    } finally {
      setBusy(false)
    }
  }

  const createOrder = async () => {
    if (busy || flow.participants.length === 0) return
    setBusy(true)
    setError('')
    setPaymentNotice(null)
    const payload = { participants: flow.participants.map(participantPayload) }
    try {
      const created = await createRegistrationOrder(payload, flow.idempotencyKey)
      const { access_token: newAccessToken, ...safeOrderSummary } = created
      const nextFlow = {
        ...flow,
        orderId: created.order_id,
        orderSummary: safeOrderSummary,
        paymentStatus: created.payment_status,
        submissionUncertain: false,
        expiresAt: Date.now() + DRAFT_LIFETIME_MS,
      }
      persistFlow(nextFlow)
      setAccessToken(newAccessToken)
      if (created.payment_status === 'paid') {
        setFlow((current) => ({ ...current, orderSummary: safeOrderSummary, paymentStatus: 'paid' }))
        clearSavedFlow()
        go('confirmation')
      } else {
        await initializeForOrder(created.order_id, newAccessToken, safeOrderSummary)
      }
    } catch (createError) {
      const uncertain = createError.statusCode === 0 || createError.statusCode >= 500
      if (uncertain) {
        persistFlow({ ...flow, submissionUncertain: true })
      }
      setError(getErrorMessage(createError, 'Your order could not be submitted. Review the details and retry.'))
    } finally {
      setBusy(false)
    }
  }

  const resumeCheckout = async () => {
    if (busy) return
    setBusy(true)
    setError('')
    setPaymentNotice(null)
    try {
      const restored = await createRegistrationOrder(
        { participants: flow.participants.map(participantPayload) },
        flow.idempotencyKey,
      )
      const { access_token: newAccessToken, ...safeOrderSummary } = restored
      setAccessToken(newAccessToken)
      const restoredOrder = await getRegistrationOrder(restored.order_id, newAccessToken)
      const normalizedItems = restoredOrder.items.map((item) => ({
        ...item,
        category_name: item.category_name_snapshot,
        fee_ngn: item.current_fee_ngn ?? item.fee_snapshot_ngn,
        price_type: item.current_price_type,
      }))
      const nextFlow = {
        ...flow,
        orderId: restored.order_id,
        orderSummary: { ...safeOrderSummary, ...restoredOrder, items: normalizedItems },
        paymentStatus: restoredOrder.payment_status,
        submissionUncertain: false,
      }
      persistFlow(nextFlow)
      if (restoredOrder.payment_status === 'paid') {
        clearSavedFlow()
        go('confirmation')
      } else {
        await initializeForOrder(restored.order_id, newAccessToken, nextFlow.orderSummary)
      }
    } catch (resumeError) {
      setError(resumeError.statusCode === 404
        ? 'This secure checkout session is expired or revoked. Start a new registration or contact the DIC team for assistance.'
        : getErrorMessage(resumeError, 'The secure checkout could not be restored. Keep this tab open and retry.'))
    } finally {
      setBusy(false)
    }
  }

  const verifyCurrentPayment = async () => {
    if (!accessToken || !flow.orderId || !flow.paymentReference || busy) return
    setBusy(true)
    setError('')
    setPaymentNotice(null)
    try {
      const result = await verifyPayment(flow.orderId, flow.paymentReference, accessToken)
      const nextFlow = { ...flow, paymentStatus: result.payment_status }
      persistFlow(nextFlow)
      if (result.payment_status === 'paid') {
        clearSavedFlow()
        go('confirmation')
      } else if (result.attempt_status === 'failed') {
        setPaymentNotice({ kind: 'error', text: 'The payment was not completed. You may start a new payment attempt.' })
      } else if (['reconcile', 'amount_mismatch'].includes(result.attempt_status)) {
        setPaymentNotice({
          kind: 'error',
          text: 'The provider reports a charge that needs administrator reconciliation. Your registration is not confirmed; do not retry payment until it has been reviewed.',
        })
      } else {
        setPaymentNotice({ kind: 'info', text: 'Payment is still pending with Paystack. Wait briefly, then verify again. Your registration is not yet confirmed.' })
      }
    } catch (verifyError) {
      setPaymentNotice({
        kind: 'error',
        text: verifyError.statusCode === 404
          ? 'This order access or payment attempt is no longer available. Restore the secure checkout session to continue.'
          : getErrorMessage(verifyError, 'Payment could not be verified. No successful registration has been recorded.'),
      })
    } finally {
      setBusy(false)
    }
  }

  const startAnotherPayment = async () => {
    if (!flow.orderId || !accessToken || busy) return
    setBusy(true)
    setError('')
    setPaymentNotice(null)
    await initializeForOrder(flow.orderId, accessToken)
    setBusy(false)
  }
  const reportCheckoutClosed = () => setPaymentNotice({
    kind: 'info',
    text: 'Checkout was closed. The provider may still be processing the transaction; verify its status before retrying or treating registration as complete.',
  })

  const participantFormAllowed = optionsState === 'ready'
    && options?.registration_is_open
    && options.categories?.length
    && !flow.orderId
  const currentStep = step === 'confirmation' && flow.paymentStatus !== 'paid' ? 'checkout' : step

  if (step === 'recovery') return <RecoveryPage />
  if (step === 'landing') {
    return <DICLanding options={options} optionsState={optionsState} onRegister={() => participantFormAllowed && add()} onRetry={retryOptions} />
  }
  if (step === 'form') {
    if (optionsState === 'loading') return <section className="dic-flow"><Container><FlowMessage>Loading current registration categories…</FlowMessage></Container></section>
    if (!participantFormAllowed) return <section className="dic-flow"><Container><FlowMessage kind="error">{optionsError || (optionsState === 'ready' && !options?.registration_is_open ? 'Registration is not currently open.' : optionsState === 'ready' ? 'No registration categories are currently available.' : 'Registration categories could not be loaded. Return to DIC and retry.')}</FlowMessage><Link className="button" to="/dic">Return to DIC</Link></Container></section>
    return <ParticipantForm key={`${editing ?? 'new'}`} initial={editing === null ? emptyParticipant : flow.participants[editing] || emptyParticipant} categories={options.categories} options={options} isEditing={editing !== null} onBack={() => editing === null ? flow.participants.length ? go('summary') : go('landing') : go('summary')} onSave={saveParticipant} />
  }
  if (step === 'summary') {
    if (!flow.participants.length) return <DICLanding options={options} optionsState={optionsState} onRegister={() => add()} onRetry={retryOptions} />
    return <RegistrationSummary flow={flow} categories={options?.categories || []} options={options} onAdd={add} onEdit={edit} onRemove={(index) => updateParticipants(flow.participants.filter((_, itemIndex) => itemIndex !== index), true)} onCheckout={() => go('checkout')} />
  }
  if (step === 'checkout' || step === 'confirmation' && currentStep === 'checkout') {
    if (!flow.participants.length) return <section className="dic-summary"><Container><div className="confirmation-box"><h1>Registration session unavailable</h1><p>{error || 'This tab no longer has the participant details needed to resume. Begin a new registration; no payment success will be assumed.'}</p><Link className="button" to="/dic">Return to DIC</Link></div></Container></section>
    return <Checkout flow={flow} categories={options?.categories || []} options={options} accessToken={accessToken} busy={busy} error={error} paymentNotice={paymentNotice} repricingOffer={repricingOffer} onAcceptRepricing={acceptRepricing} onBack={() => go('summary')} onCreateOrder={createOrder} onResume={resumeCheckout} onInitialize={startAnotherPayment} onVerify={verifyCurrentPayment} onCheckoutClosed={reportCheckoutClosed} />
  }
  return <Confirmation flow={flow} onReset={reset} />
}
