import { useEffect, useId, useRef, useState } from 'react'
import { confirmedFeedbackResult, experiencePayload, validateExperience } from '../../services/camperFeedbackForm'
import './CamperFeedbackWorld.css'

export function ExperienceRating({ id, title, options, value, onChange, optional, error }) {
  return <fieldset className="cf-rating-question" aria-describedby={error ? `${id}-error` : undefined}>
    <legend>{title}{optional && <small>Optional · choose Not applicable if needed</small>}</legend>
    <div className="cf-rating-options">{options.map(([key, label], index) => <label key={key} className={`cf-rating-choice cf-rating-tone-${index} ${value === String(key) ? 'is-selected' : ''}`}>
      <input type="radio" name={id} value={key} checked={value === String(key)} onChange={() => onChange(String(key))} aria-invalid={Boolean(error)} />
      <span className="cf-rating-mark" aria-hidden="true">{value === String(key) ? '✓' : '○'}</span><span>{label}</span>
    </label>)}</div>
    {optional && <label className="cf-not-applicable"><input type="radio" name={id} value="not_applicable" checked={value === 'not_applicable'} onChange={() => onChange('not_applicable')} />Not applicable</label>}
    {error && <p id={`${id}-error`} className="cf-field-error">{error}</p>}
  </fieldset>
}

export default function CamperExperienceForm({ channel, spec, ratings, start, end, today, onSave, demo = false }) {
  const id = useId()
  const [choices, setChoices] = useState({}), [comments, setComments] = useState({}), [recommend, setRecommend] = useState('')
  const [errors, setErrors] = useState({}), [status, setStatus] = useState('editing'), [failure, setFailure] = useState('')
  const pending = useRef(false), mounted = useRef(true), formRef = useRef(null), resultRef = useRef(null)
  const day = channel === 'final' ? end : today
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => { if (['success', 'duplicate', 'demo_complete'].includes(status)) resultRef.current?.focus() }, [status])
  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    const state = { spec, ratings, choices, comments, recommend, channel }
    const invalid = validateExperience(state)
    setErrors(invalid); setFailure('')
    if (Object.keys(invalid).length) {
      setFailure('A few answers are still needed. Please complete the highlighted questions.')
      queueMicrotask(() => formRef.current?.querySelector('[aria-invalid="true"]')?.focus())
      return
    }
    if (demo) {
      // Preview-only: do not build an API payload, call onSave, persist or send.
      setChoices({}); setComments({}); setRecommend(''); setStatus('demo_complete')
      return
    }
    pending.current = true; setStatus('sending')
    try {
      const result = await onSave(experiencePayload({ ...state, day }))
      const confirmed = confirmedFeedbackResult(result)
      if (mounted.current) { setChoices({}); setComments({}); setRecommend(''); setStatus(confirmed) }
    } catch (error) {
      if (mounted.current) { setStatus('editing'); setFailure(error.message || 'Feedback could not be sent. Your answers have not been confirmed.') }
    } finally { pending.current = false }
  }
  if (['success', 'duplicate', 'demo_complete'].includes(status)) return <section className="cf-success" role="status" ref={resultRef} tabIndex={-1}>
    <span className="cf-success-seal" aria-hidden="true">✓</span><span className="cf-eyebrow">YOUR VOICE MATTERS</span>
    <h2>{status === 'duplicate' ? 'Your feedback is already with us.' : 'Thank you for sharing your day.'}</h2>
    <p>{status === 'demo_complete' ? 'Preview complete. Nothing was sent or saved.' : status === 'duplicate' ? 'Already received for this day. Your original response was kept.' : 'Your response was received. Your thoughts help us make camp better, together.'}</p>
    {demo && <button type="button" className="cf-secondary-button" onClick={() => setStatus('editing')}>Try the demonstration again</button>}
  </section>
  // Reverse the server scale for positive-to-negative reading order; labels and
  // numeric meanings are unchanged. Preview passes its own explicit string scale.
  const options = demo ? ratings : [...ratings].sort((a,b) => Number(b[0]) - Number(a[0]))
  return <form className="cw-experience-form" ref={formRef} onSubmit={submit} noValidate>
    <div className="cf-form-intro"><div><span className="cf-eyebrow">{channel === 'final' ? 'LOOKING BACK, GROWING FORWARD' : 'A MOMENT TO REFLECT'}</span><h2>{channel === 'final' ? 'How was your camp experience?' : 'How was your day at camp?'}</h2></div><span className="cf-day-badge">{day}</span></div>
    <p className="cf-form-note">Feedback is optional. Please answer each displayed question if you choose to send it.{!demo && ' Submitted answers cannot be edited.'}</p>
    <fieldset className="cf-form-fields" disabled={status === 'sending'}>
      <input type="hidden" name="day" value={day || ''} />
      {Object.entries(spec.ratings).map(([key,label], index) => <div className={`cf-question-block cf-question-${index % 3}`} key={key}>
        <span className="cf-question-number" aria-hidden="true">{String(index + 1).padStart(2,'0')}</span>
        <ExperienceRating id={`${id}-${key}`} title={label} options={options} value={choices[key] || ''} optional={spec.optional_ratings?.includes(key)} error={errors[key]}
          onChange={value => { setChoices(current => ({ ...current, [key]:value })); setErrors(current => ({ ...current, [key]:undefined })) }} />
      </div>)}
      {Object.entries(spec.comments).map(([key,label]) => <div className="cf-comments" key={key}><label htmlFor={`${id}-comment-${key}`}>{label}</label><p id={`${id}-hint-${key}`}>A little detail can make a big difference. Please leave out names, contact information and identifying details.</p><textarea id={`${id}-comment-${key}`} name={`answer-${key}`} rows={4} maxLength={1000} value={comments[key] || ''} onChange={event=>setComments(current=>({...current,[key]:event.target.value}))} aria-describedby={`${id}-hint-${key}`} aria-invalid={Boolean(errors[`comment-${key}`])} placeholder="What made your day? What could be better?" /><small>{(comments[key] || '').length} / 1,000 characters · optional</small>{errors[`comment-${key}`] && <p className="cf-field-error">{errors[`comment-${key}`]}</p>}</div>)}
      {channel === 'final' && <ExperienceRating id={`${id}-recommend`} title="Would you suggest this camp to a friend?" options={[["yes","Yes"],["no","No"]]} value={recommend} onChange={value => { setRecommend(value); setErrors(current => ({...current,recommend:undefined})) }} error={errors.recommend} />}
      <div className="cf-send-row"><p>{demo ? 'Explore the thank-you state when you are ready.' : 'Your honest feedback helps our camp community.'}</p><button className="cf-send-button" type="submit">{status === 'sending' ? 'Sending…' : demo ? 'Preview thank-you' : 'Send feedback'}<span aria-hidden="true">↗</span></button></div>
    </fieldset>
    {failure && <p className="cf-form-error" role="alert">{failure}</p>}
    {!demo && (day < start || day > end) && <p className="cf-form-note">The server will check the allowed camp day and your eligibility before accepting feedback.</p>}
  </form>
}
