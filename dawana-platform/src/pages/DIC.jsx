import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import {
  createRegistrationOrder,
  getRegistrationOptions,
  getRegistrationOrder,
  initializePayment,
  verifyPayment,
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

function Field({ label, name, value, onChange, type = 'text', required = true, wide = false, options, placeholder, unit, min, max, step }) {
  const common = { id: name, name, value, onChange, required, 'aria-label': label, min, max, step }
  return <label className={`dic-field ${wide ? 'dic-field-wide' : ''}`} htmlFor={name}><span>{label}{required && <b> *</b>}</span>{options ? <select {...common}><option value="">Select {label.toLowerCase()}</option>{options.map((option) => typeof option === 'string' ? <option key={option} value={option}>{option}</option> : <option key={option.value} value={option.value}>{option.label}</option>)}</select> : <span className="dic-input-wrap"><input {...common} type={type} placeholder={placeholder} />{unit && <small>{unit}</small>}</span>}</label>
}

function FlowMessage({ children, kind = 'info' }) {
  if (!children) return null
  return <p className={`dic-flow-message is-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</p>
}

function RegistrationProgress({ current }) {
  const steps = [['Registration', 'form'], ['Review', 'summary'], ['Checkout', 'checkout'], ['Confirmation', 'confirmation']]
  return <nav className="dic-steps" aria-label="Registration progress">{steps.map(([label, step], index) => <div className={step === current ? 'is-current' : ''} key={step}><b>0{index + 1}</b><span>{label}</span></div>)}</nav>
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
  const fees = categories.map((category) => Number(category.fee_ngn)).filter(Number.isFinite)
  const feeSummary = fees.length
    ? fees.length === 1 || Math.min(...fees) === Math.max(...fees)
      ? formatNgn(Math.min(...fees))
      : `${formatNgn(Math.min(...fees))}–${formatNgn(Math.max(...fees))}`
    : 'Not configured'
  const configuredVenue = options?.general_information?.venue
  const venue = typeof configuredVenue === 'string' ? configuredVenue : 'To be announced'

  return <aside className="dic-info-card"><div className="dic-card-top"><span>{canRegister ? 'Registration Open' : 'Registration Information'}</span><small>Portal Status</small></div><h2>{options?.name || 'Camp Information'}</h2><dl><dt>Date</dt><dd>{options ? `${formatDate(options.camp_start_date)} – ${formatDate(options.camp_end_date)}` : 'To be announced'}</dd><dt>Venue</dt><dd>{venue}</dd><dt>Fees</dt><dd>{feeSummary}</dd></dl>{optionsState === 'error' ? <button className="button button-outline" type="button" onClick={onRetry}>Retry loading details</button> : <button className="button" type="button" onClick={onRegister} disabled={!canRegister}>Register for DIC <span aria-hidden="true">→</span></button>}<small>{status}</small></aside>
}

function DICLanding({ options, optionsState, onRegister, onRetry }) {
  return <div className="dic-page"><section className="dic-hero"><Container><div className="dic-hero-grid"><div className="dic-hero-copy"><span className="eyebrow">DARUL ISLAM CAMP · DIC</span><h1>Darul Islam Camp</h1><p className="dic-hero-lead">A major initiative of Da&apos;wãnã Islamic Foundation.</p><p>Darul Islam Camp is a platform for intensive Islamic learning, spiritual development, youth engagement, intellectual reflection, community interaction, and personal and social development.</p><span className="dic-hero-meta">✦ &nbsp; Learning · Reflection · Community</span></div><DICInfoPanel options={options} optionsState={optionsState} onRegister={onRegister} onRetry={onRetry} /></div></Container></section><section className="dic-about"><Container><span className="eyebrow">A Foundation initiative</span><h2>Learning, reflection and growth</h2><p>Darul Islam Camp brings participants together for focused Islamic learning, spiritual development, youth engagement and community interaction. It supports personal and social development through a shared space for learning and reflection.</p></Container></section><section className="dic-areas"><Container><span className="eyebrow">Camp focus</span><h2>A space to learn and develop</h2><div className="dic-area-grid">{[['01', 'Intensive Islamic learning', 'A focused platform for learning and engagement with Islamic knowledge.'], ['02', 'Spiritual development', 'Space for reflection and continued personal development.'], ['03', 'Youth engagement', 'Encouraging meaningful participation and connection among young people.'], ['04', 'Community interaction', 'Building connection through shared learning and interaction.']].map(([number, title, copy]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{copy}</p></article>)}</div></Container></section><section className="dic-process"><Container><div className="dic-register-bar"><div><strong>Darul Islam Camp registration</strong><span>{options ? `${formatDate(options.camp_start_date)} – ${formatDate(options.camp_end_date)} · ${options.registration_is_open ? 'Registration open' : 'Registration closed'}` : 'Registration information is not currently available.'}</span></div><button className="button" type="button" onClick={onRegister} disabled={optionsState !== 'ready' || !options?.registration_is_open || !options.categories?.length}>Register for DIC <span aria-hidden="true">→</span></button></div>{optionsState === 'error' && <FlowMessage kind="error">Registration information could not be loaded. Please try again later.</FlowMessage>}{optionsState === 'ready' && (!options.registration_is_open || !options.categories.length) && <FlowMessage>{options.registration_is_open ? 'No registration categories are currently available.' : 'Registration is not currently open.'}</FlowMessage>}</Container></section></div>
}

function ParticipantForm({ initial, categories, onBack, onSave, isEditing }) {
  const [participant, setParticipant] = useState(() => ({ ...emptyParticipant, ...initial }))
  const update = (event) => setParticipant((current) => ({ ...current, [event.target.name]: event.target.value }))
  const submit = (event) => { event.preventDefault(); onSave(participant) }
  const categoryOptions = categories.map((category) => {
    const ageRange = category.minimum_age === null && category.maximum_age === null
      ? ''
      : ` · ages ${category.minimum_age ?? 'any'}–${category.maximum_age ?? 'any'}`
    return {
      value: String(category.id),
      label: `${category.name} — ${formatNgn(category.fee_ngn)}${ageRange}`,
    }
  })
  const today = localDateInputValue()
  return <section className="dic-flow"><Container><p className="dic-breadcrumb"><Link to="/">Home</Link> &nbsp;›&nbsp; <Link to="/dic">DIC</Link> &nbsp;›&nbsp; Registration</p><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · DIC REGISTRATION</span><h1>{isEditing ? 'Edit participant' : 'Participant registration'}</h1><p>Each participant has an individual registration. Multiple registrations can be grouped at checkout.</p></div><aside className="dic-flow-note">Select an edition category for each participant. The server confirms the final fee when your order is created.</aside></div><RegistrationProgress current="form" /><form className="dic-form" onSubmit={submit}><h2>Participant information</h2><p>Complete the required details for this participant.</p><h3>Personal information</h3><div className="dic-form-grid"><Field label="Full Name" name="fullName" value={participant.fullName} onChange={update} wide placeholder="Enter full name" /><Field label="Address" name="address" value={participant.address} onChange={update} wide placeholder="Enter address" /><Field label="Phone" name="phone" value={participant.phone} onChange={update} type="tel" placeholder="Phone number" /><Field label="Email" name="email" value={participant.email} onChange={update} type="email" placeholder="name@example.com" /><Field label="Date of Birth" name="dob" value={participant.dob} onChange={update} type="date" max={today} /><fieldset className="dic-field dic-radio-field"><legend>Sex <b>*</b></legend><div>{['Male', 'Female'].map((sex) => <label key={sex}><input type="radio" name="sex" value={sex} checked={participant.sex === sex} onChange={update} required />{sex}</label>)}</div></fieldset><Field label="Height" name="height" value={participant.height} onChange={update} type="number" min="0.01" step="0.01" placeholder="e.g. 175" unit="cm" /><Field label="Weight" name="weight" value={participant.weight} onChange={update} type="number" min="0.01" step="0.01" placeholder="e.g. 70" unit="kg" /><Field label="Academic Status" name="academicStatus" value={participant.academicStatus} onChange={update} options={academicOptions} /><Field label="Occupation" name="occupation" value={participant.occupation} onChange={update} options={occupations} /><Field label="Marital Status" name="maritalStatus" value={participant.maritalStatus} onChange={update} options={maritalOptions} /><Field label="Registration Category" name="categoryId" value={participant.categoryId} onChange={update} options={categoryOptions} wide /></div><div className="dic-form-actions"><button className="text-link" type="button" onClick={onBack}>← Back</button><button className="button" type="submit">{isEditing ? 'Save changes' : 'Continue to summary'} <span aria-hidden="true">→</span></button></div></form></Container></section>
}

function ParticipantCard({ participant, index, category, fee, onEdit, onRemove, locked }) {
  return <article className="participant-card"><div className="participant-card-copy"><span className="participant-number">Participant {index + 1}</span><h3>{participant.fullName}</h3><span className="status-pill">{participant.academicStatus}</span><p>{participant.email} · {participant.phone}</p><p>Category: <strong>{category?.name || 'Unavailable category'}</strong></p><p>Registration fee: <strong>{fee === null ? 'Not available' : formatNgn(fee)}</strong></p></div>{!locked && <div className="participant-actions"><button type="button" onClick={onEdit}>Edit</button><button className="remove" type="button" onClick={onRemove}>Remove</button></div>}</article>
}

function RegistrationSummary({ flow, categories, onAdd, onEdit, onRemove, onCheckout, options }) {
  const locked = Boolean(flow.orderId || flow.submissionUncertain)
  const serverItems = flow.orderSummary?.items || []
  const total = flow.orderSummary
    ? flow.orderSummary.total_amount_ngn
    : flow.participants.reduce((sum, participant) => {
      const category = categories.find((item) => String(item.id) === String(participant.categoryId))
      return sum + (category ? Number(category.fee_ngn) : 0)
    }, 0)
  return <section className="dic-summary"><Container><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · DIC</span><h1>Registration summary</h1><p>Review each participant before continuing to checkout.</p></div></div><RegistrationProgress current="summary" /><FlowMessage kind={locked ? 'info' : 'error'}>{locked ? 'The submitted order is locked to protect its fee snapshots. Continue to checkout to resume payment.' : null}</FlowMessage><div className="dic-add-note"><span>Each participant is registered individually. You can group registrations in one checkout.</span>{!locked && <button className="button button-small" type="button" onClick={onAdd}>+ Add participant</button>}</div><div className="dic-summary-layout"><div><div className="dic-summary-heading"><h2>Registered participants</h2><span>{flow.participants.length} {flow.participants.length === 1 ? 'participant' : 'participants'}</span></div>{flow.participants.map((participant, index) => { const category = categories.find((item) => String(item.id) === String(participant.categoryId)); const item = serverItems[index]; const fee = item ? item.fee_ngn : category?.fee_ngn ?? null; return <ParticipantCard key={participant.id} participant={participant} index={index} category={item ? { name: item.category_name } : category} fee={fee} locked={locked} onEdit={() => onEdit(index)} onRemove={() => onRemove(index)} /> })}</div><aside className="summary-box"><h2>Registration summary</h2><p>{options?.name || 'Darul Islam Camp'}</p><hr /><div className="dic-summary-line"><span>Participants</span><strong>{flow.participants.length}</strong></div><div className="dic-summary-line"><span>{flow.orderSummary ? 'Server-calculated total' : 'Estimated total'}</span><strong>{formatNgn(total)}</strong></div><small>{flow.orderSummary ? 'This total is locked to your submitted order.' : 'The final fee is calculated by the registration service when you create your order.'}</small><button className="button" type="button" onClick={onCheckout}>{locked ? 'Continue to checkout →' : 'Continue to checkout →'}</button>{!locked && <button className="button button-outline" type="button" onClick={onAdd}>+ Add another participant</button>}</aside></div></Container></section>
}

function CheckoutSummary({ flow, categories, options }) {
  const items = flow.orderSummary?.items || []
  return <div className="checkout-summary"><h2>Registration summary</h2><p>{options?.name || 'Darul Islam Camp'}</p>{flow.participants.map((participant, index) => { const category = categories.find((item) => String(item.id) === String(participant.categoryId)); const item = items[index]; const fee = item?.fee_ngn ?? category?.fee_ngn; return <div className="checkout-row" key={participant.id}><span>{participant.fullName}<small>{item?.category_name || category?.name || 'Category unavailable'}</small></span><strong>{fee === undefined ? '—' : formatNgn(fee)}</strong></div>})}<div className="checkout-row checkout-total"><span>{flow.orderSummary ? 'Server-calculated total' : 'Estimated total'}</span><strong>{formatNgn(flow.orderSummary?.total_amount_ngn ?? flow.participants.reduce((sum, participant) => { const category = categories.find((item) => String(item.id) === String(participant.categoryId)); return sum + (category ? Number(category.fee_ngn) : 0) }, 0))}</strong></div></div>
}

function Checkout({ flow, categories, options, accessToken, busy, error, paymentNotice, onBack, onCreateOrder, onResume, onInitialize, onVerify, onCheckoutClosed }) {
  const requiresRecovery = Boolean(flow.orderId && !accessToken)
  const needsOrder = !flow.orderId
  const canVerify = Boolean(accessToken && flow.paymentReference)
  const retryingOrder = needsOrder && flow.submissionUncertain
  return <section className="dic-summary"><Container><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · REGISTRATION</span><h1>Checkout</h1><p>Review your grouped registration.</p></div></div><RegistrationProgress current="checkout" /><div className="checkout-box"><CheckoutSummary flow={flow} categories={categories} options={options} /><FlowMessage kind="error">{error}</FlowMessage><FlowMessage kind={paymentNotice?.kind || 'info'}>{paymentNotice?.text}</FlowMessage>{needsOrder && <div className="payment-placeholder"><strong>{retryingOrder ? 'Retry secure order submission' : 'Secure order creation'}</strong><p>{retryingOrder ? 'The previous request may have completed without a response. Retrying with the same idempotency key prevents creating a duplicate order.' : 'Your registration will be submitted to the Dawana registration service. The order total returned by the server is authoritative.'}</p></div>}{requiresRecovery && <div className="payment-placeholder"><strong>Secure checkout needs to be restored</strong><p>Your bearer token is never saved in browser storage. Restore this short-lived session to obtain a fresh token and resume payment. If your payment was completed, it will be checked before any new payment is offered.</p></div>}{flow.orderId && accessToken && <div className="payment-placeholder"><strong>{flow.paymentStatus === 'paid' ? 'Payment verified' : 'Paystack test-mode checkout'}</strong><p>{flow.paymentStatus === 'paid' ? 'The registration service has confirmed this payment.' : 'Checkout opens in a separate tab so this page can securely verify your payment when you return. A redirect alone never confirms payment.'}</p>{flow.paymentReference && <span>Payment reference: {flow.paymentReference}</span>}{flow.authorizationUrl && <><a className="button button-outline dic-checkout-link" href={flow.authorizationUrl} target="_blank" rel="noopener noreferrer">Open Paystack checkout in a new tab ↗</a><button className="text-link dic-checkout-closed" type="button" onClick={onCheckoutClosed}>I cancelled or closed checkout</button></>}</div>}<div className="dic-form-actions"><button className="text-link" type="button" onClick={onBack} disabled={busy}>← Back to summary</button>{needsOrder ? <button className="button" type="button" onClick={onCreateOrder} disabled={busy}>{busy ? 'Submitting secure order…' : retryingOrder ? 'Retry order submission safely →' : 'Create order and continue to payment →'}</button> : requiresRecovery ? <button className="button" type="button" onClick={onResume} disabled={busy}>{busy ? 'Restoring secure session…' : 'Restore secure checkout →'}</button> : flow.paymentStatus === 'paid' ? <button className="button" type="button" disabled>Payment confirmed</button> : canVerify ? <div className="dic-payment-actions">{flow.paymentStatus === 'failed' && <button className="button button-outline" type="button" onClick={onInitialize} disabled={busy}>{busy ? 'Starting…' : 'Try payment again'}</button>}<button className="button" type="button" onClick={onVerify} disabled={busy}>{busy ? 'Verifying with Paystack…' : 'I have returned — verify payment'}</button></div> : <button className="button" type="button" onClick={onInitialize} disabled={busy}>{busy ? 'Connecting to Paystack…' : 'Prepare Paystack checkout →'}</button>}</div></div></Container></section>
}

function Confirmation({ flow, onReset }) {
  const paid = flow.paymentStatus === 'paid'
  return <section className="dic-summary"><Container><RegistrationProgress current="confirmation" /><div className="confirmation-box"><span className="confirmation-icon" aria-hidden="true">{paid ? '✓' : '!'}</span><span className="eyebrow">{paid ? 'PAYMENT VERIFIED' : 'PAYMENT NOT VERIFIED'}</span><h1>{paid ? 'DIC registration confirmed' : 'Registration awaiting payment verification'}</h1><p>{paid ? `Your ${flow.participants.length === 1 ? 'participant registration has' : `${flow.participants.length} participant registrations have`} been confirmed by the registration service.` : 'A successful redirect is not proof of payment. Return to checkout and verify the payment with the registration service before treating this registration as complete.'}</p>{flow.orderId && <strong>Order reference: {flow.orderId}</strong>}{paid && <button className="button" type="button" onClick={onReset}>Return to DIC</button>}</div></Container></section>
}

function getStep(pathname) {
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
        fee_ngn: item.fee_snapshot_ngn,
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

  if (step === 'landing') {
    return <DICLanding options={options} optionsState={optionsState} onRegister={() => participantFormAllowed && add()} onRetry={retryOptions} />
  }
  if (step === 'form') {
    if (optionsState === 'loading') return <section className="dic-flow"><Container><FlowMessage>Loading current registration categories…</FlowMessage></Container></section>
    if (!participantFormAllowed) return <section className="dic-flow"><Container><FlowMessage kind="error">{optionsError || (optionsState === 'ready' && !options?.registration_is_open ? 'Registration is not currently open.' : optionsState === 'ready' ? 'No registration categories are currently available.' : 'Registration categories could not be loaded. Return to DIC and retry.')}</FlowMessage><Link className="button" to="/dic">Return to DIC</Link></Container></section>
    return <ParticipantForm key={`${editing ?? 'new'}`} initial={editing === null ? emptyParticipant : flow.participants[editing] || emptyParticipant} categories={options.categories} isEditing={editing !== null} onBack={() => editing === null ? flow.participants.length ? go('summary') : go('landing') : go('summary')} onSave={saveParticipant} />
  }
  if (step === 'summary') {
    if (!flow.participants.length) return <DICLanding options={options} optionsState={optionsState} onRegister={() => add()} onRetry={retryOptions} />
    return <RegistrationSummary flow={flow} categories={options?.categories || []} options={options} onAdd={add} onEdit={edit} onRemove={(index) => updateParticipants(flow.participants.filter((_, itemIndex) => itemIndex !== index), true)} onCheckout={() => go('checkout')} />
  }
  if (step === 'checkout' || step === 'confirmation' && currentStep === 'checkout') {
    if (!flow.participants.length) return <section className="dic-summary"><Container><div className="confirmation-box"><h1>Registration session unavailable</h1><p>{error || 'This tab no longer has the participant details needed to resume. Begin a new registration; no payment success will be assumed.'}</p><Link className="button" to="/dic">Return to DIC</Link></div></Container></section>
    return <Checkout flow={flow} categories={options?.categories || []} options={options} accessToken={accessToken} busy={busy} error={error} paymentNotice={paymentNotice} onBack={() => go('summary')} onCreateOrder={createOrder} onResume={resumeCheckout} onInitialize={startAnotherPayment} onVerify={verifyCurrentPayment} onCheckoutClosed={reportCheckoutClosed} />
  }
  return <Confirmation flow={flow} onReset={reset} />
}
