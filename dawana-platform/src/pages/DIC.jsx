import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'

const emptyParticipant = { fullName: '', address: '', phone: '', email: '', dob: '', sex: '', height: '', weight: '', academicStatus: '', occupation: '', maritalStatus: '' }
const academicOptions = ['Primary Student', 'Secondary Student', 'Tertiary Student', 'Graduate / Completed Tertiary Education', 'Not Currently in School']
const occupations = ['Civil Servant', 'Business', 'Trader', 'Entrepreneur']
const maritalOptions = ['Single', 'Married', 'Divorcee', 'Widow / Widower']
const routeFor = { landing: '/dic', form: '/dic/register', summary: '/dic/register/summary', checkout: '/dic/register/checkout', confirmation: '/dic/register/confirmation' }

function Field({ label, name, value, onChange, type = 'text', required = true, wide = false, options, placeholder, unit }) {
  const common = { id: name, name, value, onChange, required, 'aria-label': label }
  return <label className={`dic-field ${wide ? 'dic-field-wide' : ''}`} htmlFor={name}><span>{label}{required && <b> *</b>}</span>{options ? <select {...common}><option value="">Select {label.toLowerCase()}</option>{options.map((option) => <option key={option}>{option}</option>)}</select> : <span className="dic-input-wrap"><input {...common} type={type} placeholder={placeholder} />{unit && <small>{unit}</small>}</span>}</label>
}

function RegistrationProgress({ current }) {
  const steps = [['Registration', 'form'], ['Review', 'summary'], ['Checkout', 'checkout'], ['Confirmation', 'confirmation']]
  return <nav className="dic-steps" aria-label="Registration progress">{steps.map(([label, step], index) => <div className={step === current ? 'is-current' : ''} key={step}><b>0{index + 1}</b><span>{label}</span></div>)}</nav>
}

function DICInfoPanel({ onRegister }) {
  return <aside className="dic-info-card"><div className="dic-card-top"><span>Registration Required</span><small>Portal Status</small></div><h2>Camp Information</h2><dl><dt>Date</dt><dd>To be announced</dd><dt>Venue</dt><dd>To be announced</dd><dt>Fee</dt><dd>To be announced</dd></dl><button className="button" type="button" onClick={onRegister}>Register for DIC <span aria-hidden="true">→</span></button></aside>
}

function DICLanding({ onRegister }) {
  return <div className="dic-page"><section className="dic-hero"><Container><div className="dic-hero-grid"><div className="dic-hero-copy"><span className="eyebrow">DARUL ISLAM CAMP · DIC</span><h1>Darul Islam Camp</h1><p className="dic-hero-lead">A major initiative of Da&apos;wãnã Islamic Foundation.</p><p>Darul Islam Camp is a platform for intensive Islamic learning, spiritual development, youth engagement, intellectual reflection, community interaction, and personal and social development.</p><span className="dic-hero-meta">✦ &nbsp; Learning · Reflection · Community</span></div><DICInfoPanel onRegister={onRegister} /></div></Container></section><section className="dic-about"><Container><span className="eyebrow">A Foundation initiative</span><h2>Learning, reflection and growth</h2><p>Darul Islam Camp brings participants together for focused Islamic learning, spiritual development, youth engagement and community interaction. It supports personal and social development through a shared space for learning and reflection.</p></Container></section><section className="dic-areas"><Container><span className="eyebrow">Camp focus</span><h2>A space to learn and develop</h2><div className="dic-area-grid">{[['01', 'Intensive Islamic learning', 'A focused platform for learning and engagement with Islamic knowledge.'], ['02', 'Spiritual development', 'Space for reflection and continued personal development.'], ['03', 'Youth engagement', 'Encouraging meaningful participation and connection among young people.'], ['04', 'Community interaction', 'Building connection through shared learning and interaction.']].map(([number, title, copy]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{copy}</p></article>)}</div></Container></section><section className="dic-process"><Container><div className="dic-register-bar"><div><strong>Darul Islam Camp registration</strong><span>Date, venue and fee: To be announced.</span></div><button className="button" type="button" onClick={onRegister}>Register for DIC <span aria-hidden="true">→</span></button></div></Container></section></div>
}

function ParticipantForm({ initial, onBack, onSave, isEditing }) {
  const [participant, setParticipant] = useState(() => ({ ...emptyParticipant, ...initial }))
  const update = (event) => setParticipant((current) => ({ ...current, [event.target.name]: event.target.value }))
  const submit = (event) => { event.preventDefault(); onSave(participant) }
  return <section className="dic-flow"><Container><p className="dic-breadcrumb"><Link to="/">Home</Link> &nbsp;›&nbsp; <Link to="/dic">DIC</Link> &nbsp;›&nbsp; Registration</p><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · DIC REGISTRATION</span><h1>{isEditing ? 'Edit participant' : 'Participant registration'}</h1><p>Each participant has an individual registration. Multiple registrations can be grouped at checkout.</p></div><aside className="dic-flow-note">Camp date, venue and fee are to be announced.</aside></div><RegistrationProgress current="form" /><form className="dic-form" onSubmit={submit}><h2>Participant information</h2><p>Complete the required details for this participant.</p><h3>Personal information</h3><div className="dic-form-grid"><Field label="Full Name" name="fullName" value={participant.fullName} onChange={update} wide placeholder="Enter full name" /><Field label="Address" name="address" value={participant.address} onChange={update} wide placeholder="Enter address" /><Field label="Phone" name="phone" value={participant.phone} onChange={update} type="tel" placeholder="Phone number" /><Field label="Email" name="email" value={participant.email} onChange={update} type="email" placeholder="name@example.com" /><Field label="Date of Birth" name="dob" value={participant.dob} onChange={update} type="date" /><fieldset className="dic-field dic-radio-field"><legend>Sex <b>*</b></legend><div>{['Male', 'Female'].map((sex) => <label key={sex}><input type="radio" name="sex" value={sex} checked={participant.sex === sex} onChange={update} required />{sex}</label>)}</div></fieldset><Field label="Height" name="height" value={participant.height} onChange={update} placeholder="e.g. 175" unit="cm" /><Field label="Weight" name="weight" value={participant.weight} onChange={update} placeholder="e.g. 70" unit="kg" /><Field label="Academic Status" name="academicStatus" value={participant.academicStatus} onChange={update} options={academicOptions} /><Field label="Occupation" name="occupation" value={participant.occupation} onChange={update} options={occupations} /><Field label="Marital Status" name="maritalStatus" value={participant.maritalStatus} onChange={update} options={maritalOptions} /></div><div className="dic-form-actions"><button className="text-link" type="button" onClick={onBack}>← Back</button><button className="button" type="submit">{isEditing ? 'Save changes' : 'Continue to summary'} <span aria-hidden="true">→</span></button></div></form></Container></section>
}

function ParticipantCard({ participant, index, onEdit, onRemove }) {
  return <article className="participant-card"><div className="participant-card-copy"><span className="participant-number">Participant {index + 1}</span><h3>{participant.fullName}</h3><span className="status-pill">{participant.academicStatus}</span><p>{participant.email} · {participant.phone}</p><p>Registration fee: <strong>Fee to be announced</strong></p></div><div className="participant-actions"><button type="button" onClick={onEdit}>Edit</button><button className="remove" type="button" onClick={onRemove}>Remove</button></div></article>
}

function RegistrationSummary({ participants, onAdd, onEdit, onRemove, onCheckout }) {
  return <section className="dic-summary"><Container><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · DIC</span><h1>Registration summary</h1><p>Review each participant before continuing to checkout.</p></div></div><RegistrationProgress current="summary" /><div className="dic-add-note"><span>Each participant is registered individually. You can group registrations in one checkout.</span><button className="button button-small" type="button" onClick={onAdd}>+ Add participant</button></div><div className="dic-summary-layout"><div><div className="dic-summary-heading"><h2>Registered participants</h2><span>{participants.length} {participants.length === 1 ? 'participant' : 'participants'}</span></div>{participants.map((participant, index) => <ParticipantCard key={participant.id} participant={participant} index={index} onEdit={() => onEdit(index)} onRemove={() => onRemove(index)} />)}</div><aside className="summary-box"><h2>Registration summary</h2><p>Darul Islam Camp</p><hr /><div className="dic-summary-line"><span>Participants</span><strong>{participants.length}</strong></div><div className="dic-summary-line"><span>Total fee</span><strong>To be announced</strong></div><small>Fees vary by academic category. Official amounts have not yet been announced.</small><button className="button" type="button" onClick={onCheckout}>Continue to checkout →</button><button className="button button-outline" type="button" onClick={onAdd}>+ Add another participant</button></aside></div></Container></section>
}

function CheckoutSummary({ participants }) {
  return <div className="checkout-summary"><h2>Registration summary</h2>{participants.map((participant) => <div className="checkout-row" key={participant.id}><span>{participant.fullName}<small>{participant.academicStatus}</small></span><strong>Fee to be announced</strong></div>)}<div className="checkout-row checkout-total"><span>Total</span><strong>To be announced</strong></div></div>
}

function Checkout({ participants, onBack, onConfirm }) {
  return <section className="dic-summary"><Container><div className="dic-flow-hero"><div><span className="eyebrow">DARUL ISLAM CAMP · REGISTRATION</span><h1>Checkout</h1><p>Review your grouped registration.</p></div></div><RegistrationProgress current="checkout" /><div className="checkout-box"><CheckoutSummary participants={participants} /><div className="payment-placeholder"><strong>Payment setup</strong><p>Payment will be available when official fees and a payment provider are configured. No payment is collected in this prototype.</p><span>Payment method: To be announced</span></div><div className="dic-form-actions"><button className="text-link" type="button" onClick={onBack}>← Back to summary</button><button className="button" type="button" onClick={onConfirm}>Complete prototype registration →</button></div></div></Container></section>
}

function Confirmation({ participants, onReset }) {
  return <section className="dic-summary"><Container><RegistrationProgress current="confirmation" /><div className="confirmation-box"><span className="confirmation-icon" aria-hidden="true">✓</span><span className="eyebrow">Prototype registration complete</span><h1>DIC registration received</h1><p>Your {participants.length === 1 ? 'participant registration has' : `${participants.length} participant registrations have`} been completed in this frontend prototype. No payment has been made.</p><strong>Reference: No transaction or registration ID assigned</strong><button className="button" type="button" onClick={onReset}>Return to DIC</button></div></Container></section>
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
  const [participants, setParticipants] = useState([])
  const [editing, setEditing] = useState(null)
  const go = (next) => navigate(routeFor[next])
  const save = (participant) => { setParticipants((current) => editing === null ? [...current, { ...participant, id: crypto.randomUUID() }] : current.map((item, index) => index === editing ? { ...participant, id: item.id } : item)); setEditing(null); go('summary') }
  const add = () => { setEditing(null); go('form') }
  const edit = (index) => { setEditing(index); go('form') }
  const reset = () => { setParticipants([]); setEditing(null); go('landing') }
  if (step === 'landing') return <DICLanding onRegister={add} />
  if (step === 'form') return <ParticipantForm key={`${editing ?? 'new'}`} initial={editing === null ? emptyParticipant : participants[editing] || emptyParticipant} isEditing={editing !== null} onBack={() => editing === null ? participants.length ? go('summary') : go('landing') : go('summary')} onSave={save} />
  if (step === 'summary') return participants.length ? <RegistrationSummary participants={participants} onAdd={add} onEdit={edit} onRemove={(index) => setParticipants((current) => current.filter((_, i) => i !== index))} onCheckout={() => go('checkout')} /> : <DICLanding onRegister={add} />
  if (step === 'checkout') return participants.length ? <Checkout participants={participants} onBack={() => go('summary')} onConfirm={() => go('confirmation')} /> : <DICLanding onRegister={add} />
  return participants.length ? <Confirmation participants={participants} onReset={reset} /> : <DICLanding onRegister={add} />
}
