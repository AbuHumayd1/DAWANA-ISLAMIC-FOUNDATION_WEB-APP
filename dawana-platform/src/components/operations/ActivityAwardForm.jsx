import { useEffect, useRef, useState } from 'react'
import { getOperationsData } from '../../services/operationsApi'
import { submissionReference } from '../../services/houseScoring'
import { activityScoringPath, activityPayload, campToday, participationPreview } from '../../services/activityScoring'

const empty = () => ({ activity: '', date: campToday(), participant: '', house: '', slot: '', reading_target: '', note: '', verified: false, attendees: [], exemptions: {}, marks: {} })

export default function ActivityAwardForm({ edition, busy, canCorrect, onSave, mode = 'house' }) {
  const [options, setOptions] = useState(null), [error, setError] = useState(''), [values, setValues] = useState(empty)
  const [refresh, setRefresh] = useState(0)
  const reference = useRef(null)
  useEffect(() => {
    const controller = new AbortController()
    getOperationsData(activityScoringPath(edition), { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return
      setOptions(result)
      setValues(current => ({ ...current, date: result.start_date > campToday() ? result.start_date : (current.date < result.start_date || current.date > result.end_date ? campToday() : current.date) }))
    }).catch(failure => { if (!controller.signal.aborted) setError(failure.message) })
    return () => controller.abort()
  }, [edition, refresh])
  const change = (key, value) => setValues(current => ({ ...current, [key]: value }))
  const activities = mode === 'individual' ? options?.individual || [] : options?.collective || []
  const rule = activities.find(row => row.code === values.activity)
  const beforeCamp = !!options && campToday() < options.start_date
  const collective = rule?.kind === 'collective'
  const roster = options?.members.filter(row => row.house === Number(values.house)) || []
  const participation = ['participation', 'prayer_target'].includes(rule?.mode)
  const preview = participationPreview(roster, values.attendees, values.exemptions)
  async function submit(event) {
    event.preventDefault(); setError('')
    try {
      const payload = activityPayload(values, rule, options.members, options.houses)
      reference.current = submissionReference(reference.current, payload)
      if (await onSave({ ...payload, request_id: reference.current.id })) {
        reference.current = null
        setValues(current => ({ ...empty(), activity: current.activity, date: current.date }))
        setRefresh(current => current + 1)
      }
    } catch (failure) { setError(failure.message) }
  }
  return <section className="ops-panel activity-award-panel"><h2>{mode === 'individual' ? 'Award individual points' : 'Verified collective house activities'}</h2>
    <p>{mode === 'individual' ? 'Choose a checked-in, eligible camper and an approved achievement. The official catalogue fixes the point value and credits the house once.' : 'Record verified collective achievements using the existing approved activity catalogue.'}</p>
    {error && <p role="alert" className="ops-error">{error} <button type="button" className="ops-button" onClick={() => { setError(''); setRefresh(current => current + 1) }}>Reload activity options</button></p>}
    {!options ? <p role="status">Loading eligible campers and approved activities…</p> : <>
      {!options.storage_ready && <p className="ops-callout" role="status">Activity scoring is awaiting its approved database setup. No activity awards can be submitted yet.</p>}
      {!options.ready && <p className="ops-callout" role="status">{options.message}</p>}
      {mode === 'individual' && <div className="score-roster-panel"><div><strong>Eligible checked-in campers</strong><p>Visible here before selecting an activity. This is not a points award and does not modify check-in or allocation.</p></div><span className="score-roster-count">{options.members.length} eligible</span>
        {options.members.length ? <ul>{options.members.map(member => <li key={member.id}><span>{member.name}</span><small>{member.house_name} · Checked in and allocated</small></li>)}</ul> : <p role="status">No campers currently meet all scoring requirements. Verify payment, check-in, house allocation and registration eligibility in Operations.</p>}
      </div>}
      {beforeCamp && <p role="status" className="score-policy-note">Camp activity awards open on {options.start_date} (Africa/Lagos). Existing early check-ins and house allocations remain valid, but no points can be entered before camp begins.</p>}
      <form className="score-form" onSubmit={submit}><fieldset disabled={busy || beforeCamp || !options.storage_ready || !options.ready}>
        {mode === 'individual' && <label>Eligible camper<select required value={values.participant} onChange={event => change('participant',event.target.value)}><option value="">Choose a checked-in camper</option>{options.members.map(row => <option key={row.id} value={row.id}>{row.name} · {row.house_name}</option>)}</select></label>}
        <label>Approved activity<select required value={values.activity} onChange={event => { setValues(current => ({ ...empty(), date: current.date, participant: current.participant, activity: event.target.value })); reference.current = null }}>
          <option value="">Choose an approved {mode === 'individual' ? 'individual' : 'collective'} activity</option>
          {activities.map(row => <option key={row.code} value={row.code}>{row.code} · {row.name} (+{row.points})</option>)}
        </select></label>
        <label>Camp-local activity date<input type="date" required min={options.start_date} max={options.end_date < campToday() ? options.end_date : campToday()} value={values.date} onChange={event => change('date', event.target.value)} /></label>
        {rule && <>
          <p className="score-wide">Award: <strong>{rule.points} points</strong>{rule.threshold && ` · Required participation: ${rule.threshold}%`}{rule.cap_bucket && ` · Separate daily ${rule.cap_bucket} cap: 10`}{rule.frequency === 'once' && ' · Once per camper this edition; verified prerequisites required.'}</p>
          {collective ? <label>House<select required value={values.house} onChange={event => setValues(current => ({ ...current, house: event.target.value, attendees: [], exemptions: {} }))}><option value="">Choose a house</option>{options.houses.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
            : null}
          {['prayer', 'rawatib'].includes(rule.frequency) && <label>{rule.frequency === 'rawatib' ? 'Rawātib period' : 'Obligatory prayer'}<select required value={values.slot} onChange={event => change('slot', event.target.value)}><option value="">Choose a period</option>{options[rule.frequency === 'rawatib' ? 'rawatib' : 'prayers'].map(slot => <option key={slot} value={slot}>{slot.replaceAll('_', ' ')}</option>)}</select></label>}
          {['target', 'session'].includes(rule.frequency) && <label>Approved target / task / incident / session reference<input required maxLength={80} pattern="[a-z0-9][a-z0-9_-]*" value={values.slot} onChange={event => change('slot', event.target.value)} /><small>Use the same agreed lowercase reference for the same achievement, including when another officer records it. Never relabel a task or incident to award it twice.</small></label>}
          {rule.code === 'MIL05' && <label>Completed approved reading target<input required maxLength={80} pattern="[a-z0-9][a-z0-9_-]*" value={values.reading_target} onChange={event => change('reading_target', event.target.value)} /><small>Must match a verified QUR05 reading task.</small></label>}
          {collective && participation && values.house && <div className="score-wide activity-roster"><h3>Verified participation and approved exemptions</h3>
            <p>Denominator: checked-in eligible members minus approved exemptions. The server rechecks the roster at submission.</p>
            {rule.mode === 'prayer_target' && <p>Participants are calculated from verified SAL01/SAL02 awards for at least four distinct prayers on this date.</p>}
            {roster.map(member => <div className="activity-member" key={member.id}>
              {rule.mode === 'prayer_target' ? <span>{member.name}</span> : <label className="activity-check"><input type="checkbox" checked={values.attendees.includes(member.id)} disabled={values.exemptions[member.id] !== undefined} onChange={event => change('attendees', event.target.checked ? [...values.attendees, member.id] : values.attendees.filter(id => id !== member.id))} />{member.name}</label>}
              {canCorrect && <><label className="activity-check"><input type="checkbox" checked={values.exemptions[member.id] !== undefined} onChange={event => { const exemptions = { ...values.exemptions }; if (event.target.checked) exemptions[member.id] = ''; else delete exemptions[member.id]; change('exemptions', exemptions) }} />Approved exemption</label>
                {values.exemptions[member.id] !== undefined && <input required maxLength={300} aria-label={`Approved exemption reason for ${member.name}`} placeholder="Document the approved reason" value={values.exemptions[member.id]} onChange={event => change('exemptions', { ...values.exemptions, [member.id]: event.target.value })} />}</>}
            </div>)}
            {!roster.length && <p>No currently eligible checked-in members.</p>}
            <p>{rule.mode === 'prayer_target' ? `${preview.denominator} non-exempt eligible members; punctuality calculated on the server.` : `${preview.numerator} / ${preview.denominator} participating${preview.percentage === null ? ' · No qualifying denominator' : ` · ${preview.percentage.toFixed(1)}% (preview)`}`}</p>
          </div>}
          {collective && ['inspection', 'competition'].includes(rule.mode) && <div className="score-wide activity-results"><h3>Verified official assessment marks</h3><p>Highest marks win; tied winners receive the full fixed bonus. Inspection results must include all houses. For competitions, leave non-participating houses blank. Reuse identical results when recording each tied winner.</p>
            {options.houses.map(house => <label key={house.id}>{house.name}<input type="number" min="0" max="99999999.99" step="0.01" required={rule.mode === 'inspection'} value={values.marks[house.id] || ''} onChange={event => change('marks', { ...values.marks, [house.id]: event.target.value })} /></label>)}
          </div>}
          <label className="score-wide">Verification evidence / note<textarea required={collective || rule.frequency === 'target'} maxLength={600} rows={3} value={values.note} onChange={event => change('note', event.target.value)} /></label>
          <label className="score-wide activity-check"><input type="checkbox" required checked={values.verified} onChange={event => change('verified', event.target.checked)} />I have verified completion, the approved target or official result, and any documented exemptions.</label>
          <button className="ops-button ops-button-primary" disabled={!options.ready || !options.storage_ready}>Record verified award</button>
        </>}
      </fieldset></form>
    </>}
  </section>
}
