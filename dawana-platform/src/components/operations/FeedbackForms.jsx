import { useRef, useState } from 'react'
import { submissionReference } from '../../services/houseScoring'
import { feedbackChannels } from '../../services/feedback'

export function ExperienceForm({ channel, spec, ratings, start, end, onSave, today }) {
  const [busy,setBusy]=useState(false), [message,setMessage]=useState('')
  const pending=useRef(false)
  async function submit(event) {
    event.preventDefault(); if(pending.current)return
    const form=event.currentTarget, values=new FormData(form)
    const payload={channel,day:values.get('day'),ratings:{},answers:{}}
    for(const key of Object.keys(spec.ratings))if(values.get(`rating-${key}`)!=='not_applicable')payload.ratings[key]=Number(values.get(`rating-${key}`))
    for(const key of Object.keys(spec.comments))payload.answers[key]=values.get(`answer-${key}`)||''
    if(channel==='final')payload.recommend=values.get('recommend')==='yes'
    pending.current=true;setBusy(true);setMessage('')
    try { const result=await onSave(payload);setMessage(result.duplicate?'Already received for this day. Your original response was kept.':'Thank you. Your response was received.');if(!result.duplicate)form.reset() }
    catch(error){setMessage(error.message)}finally{pending.current=false;setBusy(false)}
  }
  return <section className="ops-panel feedback-form"><h2>{feedbackChannels[channel]}</h2><form onSubmit={submit}><fieldset disabled={busy}>
    <p>Feedback is optional. Submitted answers cannot be edited.</p>
    <label>Camp day<input name="day" type="date" required min={start} max={end} defaultValue={channel==='final'?end:channel==='daily'?today:undefined} readOnly={channel==='final'||channel==='daily'} /></label>
    {Object.entries(spec.ratings).map(([key,label])=><label key={key}>{label}<select name={`rating-${key}`} required defaultValue=""><option value="">Choose a rating</option>{ratings.map(([value,text])=><option value={value} key={value}>{text}</option>)}{spec.optional_ratings?.includes(key)&&<option value="not_applicable">Not applicable</option>}</select></label>)}
    {Object.entries(spec.comments).map(([key,label])=><label key={key}>{label}<textarea name={`answer-${key}`} rows={2} maxLength={1000} /></label>)}
    {channel==='final'&&<label>Would you suggest this camp to a friend?<select name="recommend" required defaultValue=""><option value="">Choose</option><option value="yes">Yes</option><option value="no">No</option></select></label>}
    <button className="ops-button ops-button-primary">{busy?'Sending…':'Send feedback'}</button>
  </fieldset></form><p role="status" aria-live="polite">{message}</p></section>
}

export function WelfareForm({ categories, urgent, onSave, reporterNotice }) {
  const [busy,setBusy]=useState(false), [message,setMessage]=useState('')
  const pending=useRef(false), reference=useRef(null)
  async function submit(event) {
    event.preventDefault();if(pending.current)return
    const form=event.currentTarget, values=new FormData(form)
    const payload={category:values.get('category'),description:values.get('description'),assistance_person:values.get('assistance_person')||'',urgency:values.get('urgency'),preferred_contact:values.get('preferred_contact')}
    pending.current=true;setBusy(true);setMessage('')
    try { reference.current=submissionReference(reference.current,payload);const result=await onSave({...payload,request_id:reference.current.id});setMessage(result.duplicate?'This report was already received.':'Your welfare report was received. Contact an officer directly if you need urgent help.');reference.current=null;form.reset() }
    catch(error){setMessage(error.message)}finally{pending.current=false;setBusy(false)}
  }
  return <section className="ops-panel feedback-form"><h2>Confidential welfare assistance</h2><p className="ops-callout">{urgent}</p><p>{reporterNotice}</p><form onSubmit={submit}><fieldset disabled={busy}>
    <label>Category<select name="category" required defaultValue=""><option value="">Choose</option>{Object.entries(categories).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label>
    <label>What help is needed?<textarea name="description" required maxLength={5000} rows={4} /></label>
    <label>Urgency<select name="urgency" defaultValue="normal"><option value="normal">Normal</option><option value="urgent">Urgent — also contact a camp official immediately</option></select></label>
    <label>Preferred contact method<select name="preferred_contact" defaultValue="none"><option value="none">No preference</option><option value="in_person">In person</option><option value="email">Verified booking email, where available</option></select></label>
    <label>Person needing assistance, if different from you<input name="assistance_person" maxLength={200} /></label>
    <button className="ops-button ops-button-primary">{busy?'Sending…':'Send confidential report'}</button>
  </fieldset></form><p role="status" aria-live="polite">{message}</p></section>
}
