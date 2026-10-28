import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getOperationsData, postOperationsData, getScoringPrintUrl } from '../services/operationsApi'
import { scoringPath, scorePayload, submissionReference } from '../services/houseScoring'
import { checkInTime } from '../services/checkIn'
import ActivityAwardForm from '../components/operations/ActivityAwardForm'
import { activityScoringPath } from '../services/activityScoring'

export function CombinedLeaderboard({ rows }) {
  return <><p className="score-caption">Combined house leaderboard — male and female houses</p>
    <div className="ops-table-wrap score-table-scroll" role="region" aria-label="Combined house leaderboard" tabIndex={0}><table className="ops-table score-leaderboard" aria-label="Combined house leaderboard">
    <colgroup><col className="score-rank-column" /><col /><col className="score-number-column" /><col className="score-number-column" /><col className="score-number-column" /></colgroup>
    <thead><tr><th scope="col">Rank</th><th scope="col">House</th><th scope="col">Awarded</th><th scope="col">Deducted</th><th scope="col">Net score</th></tr></thead>
    <tbody>{rows.map(row => <tr key={row.house_id}><td>{row.rank}</td><td><span className="score-house">{row.colour && <span className="score-swatch" style={{ backgroundColor: row.colour }} aria-hidden="true" />}<span>{row.name}</span></span>{!row.colour && <small className="score-colour-note">Colour not configured</small>}</td><td>{row.awarded}</td><td>{row.deducted}</td><td><strong>{row.net}</strong></td></tr>)}</tbody>
  </table></div>{!rows.length && <p>No participant houses configured for this edition. Ask an administrator to review the existing house setup.</p>}</>
}

export function ScoreHistory({ rows, canCorrect, busy, onReverse }) {
  return <div className="score-history">{rows.map(row => <article key={row.id} className="score-history-entry">
    <div><h3>#{row.id} · {row.house}</h3><p><strong>{row.entry_type === 'award' ? 'Award' : 'Deduction'}: {row.points}</strong> · {row.activity}</p>
      <p>{row.staff} · {checkInTime(row.time)}</p>{row.note && <p>{row.note}</p>}
      {row.reverses && <p>Correction: reverses entry #{row.reverses}.</p>}{row.reversed_by && <p>Reversed by entry #{row.reversed_by}. Original entry retained.</p>}</div>
    {canCorrect && !row.reverses && !row.reversed_by && <button type="button" className="ops-button ops-button-secondary" disabled={busy} onClick={() => onReverse(row)}>Reverse entry</button>}
  </article>)}{!rows.length && <p>No scoring entries yet. Every configured house starts at zero.</p>}</div>
}

function ScoreEntryForm({ houses, busy, onSave }) {
  const [values, setValues] = useState({ house: '', entry_type: 'award', points: '', activity: '', note: '' })
  const [error, setError] = useState('')
  const reference = useRef(null)
  const change = event => setValues(current => ({ ...current, [event.target.name]: event.target.value }))
  async function submit(event) {
    event.preventDefault(); setError('')
    try {
      const payload = scorePayload(values)
      reference.current = submissionReference(reference.current, payload)
      if (await onSave({ ...payload, request_id: reference.current.id })) {
        reference.current = null
        setValues(current => ({ ...current, points: '', activity: '', note: '' }))
      }
    } catch (failure) { setError(failure.message) }
  }
  return <section className="ops-panel"><h2>Award / Deduct Points</h2><p>Direct house awards and deductions for other agreed reasons. Use the verified activity selector above for catalogue awards; direct entries do not add personal points.</p>
    <form className="score-form" onSubmit={submit}><fieldset disabled={busy || !houses.length}>
      <label>House<select name="house" required value={values.house} onChange={change}><option value="">Choose a house</option>{houses.map(row => <option key={row.house_id} value={row.house_id}>{row.name}</option>)}</select></label>
      <label>Transaction type<select name="entry_type" value={values.entry_type} onChange={change}><option value="award">Award</option><option value="deduction">Deduction</option></select></label>
      <label>Points<input name="points" type="number" min="1" max="2147483647" step="1" required value={values.points} onChange={change} /></label>
      <label>Activity or reason<input name="activity" required maxLength={200} value={values.activity} onChange={change} /></label>
      <label className="score-wide">Note (optional)<textarea name="note" rows={2} maxLength={1000} value={values.note} onChange={change} /></label>
      <button className="ops-button ops-button-primary" type="submit">{busy ? 'Saving…' : 'Record points'}</button>
    </fieldset>{error && <p role="alert">{error}</p>}</form></section>
}

function ReversalForm({ entry, busy, onSave, onCancel }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const reference = useRef(null)
  async function submit(event) {
    event.preventDefault(); setError('')
    if (!reason.trim()) { setError('Explain why this entry needs reversing.'); return }
    const payload = { reason: reason.trim() }
    try {
      reference.current = submissionReference(reference.current, payload)
      await onSave(entry.id, { ...payload, request_id: reference.current.id })
    } catch (failure) { setError(failure.message) }
  }
  return <section className="ops-panel score-correction"><h2>Reverse entry #{entry.id}</h2><p>{entry.house}: {entry.entry_type} {entry.points} points for {entry.activity}. This adds equal opposing points and retains the original record. Record a new entry afterwards if a replacement is needed.</p>
    <form className="score-form" onSubmit={submit}><label>Reason for correction<textarea required maxLength={1000} rows={2} value={reason} disabled={busy} onChange={event => setReason(event.target.value)} /></label>
      <div className="score-actions"><button className="ops-button ops-button-primary" disabled={busy}>Confirm reversal</button><button type="button" className="ops-button ops-button-secondary" disabled={busy} onClick={onCancel}>Cancel</button></div>{error && <p role="alert">{error}</p>}</form>
  </section>
}

export default function HouseScoring({ user }) {
  const [params, setParams] = useSearchParams()
  const edition = params.get('edition') || '', page = Number(params.get('page') || 1)
  const [state, setState] = useState({ path: '', data: null, error: '' })
  const [refresh, setRefresh] = useState(0), [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState({ path: '', message: '' }), [correction, setCorrection] = useState(null)
  const posting = useRef(false), currentPath = useRef('')
  let path, pathError
  try { path = scoringPath(edition, page) } catch (failure) { pathError = failure.message }
  useEffect(() => { currentPath.current = path; return () => { currentPath.current = '' } }, [path])
  useEffect(() => {
    if (!path) return
    let live = true
    const controller = new AbortController()
    getOperationsData(path, { signal: controller.signal }).then(data => {
      if (live) setState({ path, data, error: '' })
    }).catch(failure => { if (live) setState({ path, data: null, error: failure.message }) })
    return () => { live = false; controller.abort() }
  }, [path, refresh])
  const error = pathError || (state.path === path ? state.error : '')
  const data = !error && state.path === path ? state.data : null
  function reload() { setRefresh(value => value+1) }
  function changePage(nextEdition, nextPage = 1) {
    setCorrection(null); setParams({ ...(nextEdition ? { edition: String(nextEdition) } : {}), page: String(nextPage) })
  }
  async function save(payload, entryId = null, activity = false) {
    if (posting.current || !data?.edition) return false
    posting.current = true; setBusy(true); setNotice({ path: '', message: '' })
    const submittedPath = path
    try {
      const endpoint = entryId ? `/scoring/${entryId}/reverse/?edition=${data.edition.id}` : activity ? activityScoringPath(data.edition.id) : scoringPath(data.edition.id)
      const result = await postOperationsData(endpoint, payload)
      if (currentPath.current === submittedPath) {
        setNotice({ path: submittedPath, message: result.created ? (entryId ? 'Entry reversed. The original remains in history.' : 'Points recorded.') : 'This submission was already saved. No duplicate was added.' })
        setCorrection(null); reload()
      }
      return true
    } catch (failure) {
      if (currentPath.current === submittedPath) setNotice({ path: submittedPath, message: failure.message })
      return false
    } finally { posting.current = false; setBusy(false) }
  }
  return <>
    <div className="ops-page-heading"><div><span className="ops-eyebrow">DIC camp activities</span><h1>House Scoring</h1><p>One combined ranking for male and female houses.</p></div></div>
    <p role="status" aria-live="polite">{notice.path === path ? notice.message : ''}</p>
    {error ? <section className="ops-error" role="alert"><p>{error}</p><button className="ops-button" onClick={reload}>Retry</button><button className="ops-button" onClick={() => changePage('')}>Use current edition</button></section>
      : !data ? <p role="status" aria-busy="true">Loading house scores…</p> : <>
        <div className="ops-panel score-actions"><label className="score-edition">Camp edition<select value={data.edition?.id || ''} disabled={busy} onChange={event => changePage(event.target.value)}>
          {!data.edition && <option value="">No camp edition configured</option>}{data.editions.map(row => <option key={row.id} value={row.id}>{row.name} ({row.year})</option>)}
        </select></label><button className="ops-button ops-button-secondary" disabled={busy} onClick={reload}>Refresh</button>
          {data.edition && user.permissions.export_reports && <><a className="ops-button ops-button-secondary" target="_blank" rel="noopener noreferrer" href={getScoringPrintUrl(data.edition.id, 'leaderboard')}>Print leaderboard</a><a className="ops-button ops-button-secondary" target="_blank" rel="noopener noreferrer" href={getScoringPrintUrl(data.edition.id, 'history')}>Print history</a></>}
        </div>
        {data.edition ? <>
          <p className="campsite-context">Showing <strong>{data.edition.name}</strong>. Equal scores share ranks (1, 1, 3); names and house IDs determine display order within ties.</p>
          {data.leaderboard.length !== 8 && <p className="ops-callout" role="status">This edition has {data.leaderboard.length} participant houses configured; eight are expected. All configured participant houses are shown. Ask an administrator to review house setup.</p>}
          <section className="ops-panel"><h2>Combined leaderboard</h2><CombinedLeaderboard rows={data.leaderboard} /><p className="ops-small-note">Totals include original entries and their opposing reversals. No houses or colours are generated automatically.</p></section>
          {user.permissions.record_scores && <ActivityAwardForm key={`activity-${data.edition.id}`} edition={data.edition.id} busy={busy} canCorrect={user.permissions.correct_scores} onSave={payload => save(payload, null, true)} />}
          {user.permissions.record_scores ? <ScoreEntryForm key={data.edition.id} houses={data.leaderboard} busy={busy} onSave={payload => save(payload)} /> : <p className="ops-small-note">You have read-only access to point entry.</p>}
          {correction?.edition === data.edition.id && user.permissions.correct_scores && <ReversalForm key={correction.entry.id} entry={correction.entry} busy={busy} onCancel={() => setCorrection(null)} onSave={(id, payload) => save(payload, id)} />}
          <section className="ops-panel"><h2>Recent scoring history</h2><ScoreHistory rows={data.history} canCorrect={user.permissions.correct_scores} busy={busy} onReverse={entry => setCorrection({ edition: data.edition.id, entry })} />
            {data.count > 0 && <div className="checkin-pagination"><button className="ops-button ops-button-secondary" disabled={busy || page <= 1} onClick={() => changePage(data.edition.id, page-1)}>Previous</button><span>Page {page} of {Math.ceil(data.count / data.page_size)} · {data.count} entries</span><button className="ops-button ops-button-secondary" disabled={busy || page * data.page_size >= data.count} onClick={() => changePage(data.edition.id, page+1)}>Next</button></div>}
          </section>
        </> : <section className="ops-panel"><p>No camp edition configured. Ask an administrator to review camp setup.</p></section>}
      </>}
  </>
}
