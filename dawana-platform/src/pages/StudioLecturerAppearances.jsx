import { useCallback, useEffect, useState } from 'react'
import {
  studioLecturerAppearances, studioCreateLecturerAppearance,
  studioEditLecturerAppearance, studioActOnLecturerAppearance,
} from '../services/mediaStudioApi'
import './StudioLecturerAppearances.css'

const emptyForm = {
  lecturer: '', edition: '', participation_type: 'previous',
  topic: '', verification_note: '', confirmation_status: 'pending',
  featured: false, display_order: 0,
}
const actions = {
  verify: 'Verify evidence', publish: 'Publish to DIC page',
  withdraw: 'Withdraw from DIC page',
}

function errorMessage(error) {
  if (error?.message) return error.message
  return 'The requested operation could not be completed.'
}

export default function StudioLecturerAppearances() {
  const [data, setData] = useState({items: [], lecturers: [], editions: []})
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(emptyForm)

  const refresh = useCallback(async (target = page) => {
    setLoading(true)
    try {
      const result = await studioLecturerAppearances(target)
      setData(result)
      setPage(target)
    } catch (error) {
      setMessage(errorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [page])
  useEffect(() => { refresh(1) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function startCreate() {
    setEditing('new')
    setForm({...emptyForm, edition: data.editions[0] ? String(data.editions[0].id) : ''})
    setMessage('')
  }
  function startEdit(item) {
    setEditing(item.id)
    setForm({
      lecturer: String(item.lecturer), edition: String(item.edition),
      participation_type: item.participation_type, topic: item.topic || '',
      verification_note: item.verification_note || '',
      confirmation_status: item.confirmation_status,
      featured: Boolean(item.featured), display_order: item.display_order || 0,
    })
    setMessage('')
  }
  async function save(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setMessage('')
    try {
      const payload = {...form, lecturer: Number(form.lecturer), edition: Number(form.edition),
        display_order: Number(form.display_order)}
      if (editing === 'new') {
        await studioCreateLecturerAppearance(payload)
        setMessage('Lecturer appearance saved as a private draft. Verify evidence and publish separately.')
      } else {
        delete payload.lecturer
        delete payload.edition
        if (payload.confirmation_status === 'confirmed') delete payload.confirmation_status
        await studioEditLecturerAppearance(editing, payload)
        setMessage('Appearance details saved. Published records return to review before republication.')
      }
      setEditing(null)
      await refresh(1)
    } catch (error) { setMessage(errorMessage(error)) }
    finally { setBusy(false) }
  }
  async function act(item, action) {
    if (busy) return
    const actionLabel = actions[action]
    if (action === 'publish' && item.participation_type === 'previous' && !item.verified &&
        !window.confirm('This previous lecturer is not verified. Publishing the profile is allowed, but its lecture topic will remain hidden. Continue?')) return
    setBusy(true); setMessage('')
    try {
      await studioActOnLecturerAppearance(item.id, action)
      setMessage(actionLabel + ' completed.')
      await refresh(page)
    } catch (error) { setMessage(errorMessage(error)) }
    finally { setBusy(false) }
  }

  return <section className="studio-appearance-workflow" aria-label="Create and publish lecturer appearances">
    <div className="studio-appearance-workflow-head">
      <div>
        <span className="studio-kicker">DIC LECTURER SHOWCASE</span>
        <h3>Camp appearances</h3>
        <p>Add a lecturer to a past or upcoming DIC edition. These records feed the existing public lecturer showcase; its design is unchanged.</p>
      </div>
      {data.can_create && <button type="button" className="studio-appearance-primary" disabled={busy} onClick={startCreate}>+ New appearance</button>}
    </div>
    {message && <p className="studio-appearance-message" role="status">{message}</p>}
    {editing !== null && <form className="studio-appearance-form" onSubmit={save}>
      <div className="studio-appearance-form-header">
        <strong>{editing === 'new' ? 'New lecturer appearance' : 'Edit lecturer appearance'}</strong>
        <button type="button" disabled={busy} onClick={() => setEditing(null)} aria-label="Close appearance form">✕</button>
      </div>
      <div className="studio-appearance-fields">
        <label>Lecturer profile
          <select required disabled={busy || editing !== 'new'} value={form.lecturer} onChange={e => setForm(f => ({...f, lecturer: e.target.value}))}>
            <option value="">Choose an existing lecturer</option>
            {data.lecturers.map(person => <option value={person.id} key={person.id}>{person.name}{person.designation ? ' — ' + person.designation : ''}</option>)}
          </select>
        </label>
        <label>Camp edition
          <select required disabled={busy || editing !== 'new'} value={form.edition} onChange={e => setForm(f => ({...f, edition: e.target.value}))}>
            <option value="">Choose edition</option>
            {data.editions.map(edition => <option value={edition.id} key={edition.id}>{edition.name} ({edition.year})</option>)}
          </select>
        </label>
        <label>Appearance
          <select disabled={busy} value={form.participation_type} onChange={e => setForm(f => ({...f, participation_type: e.target.value}))}>
            <option value="previous">Previous lecturer</option>
            <option value="upcoming">Upcoming lecturer</option>
          </select>
        </label>
        <label>Participation status
          <select disabled={busy} value={form.confirmation_status} onChange={e => setForm(f => ({...f, confirmation_status: e.target.value}))}>
            <option value="pending">Pending verification</option>
            <option value="invited">Invited</option>
            <option value="declined">Declined</option>
            {form.confirmation_status === 'confirmed' && <option value="confirmed" disabled>Confirmed — verified</option>}
          </select>
        </label>
        <label className="studio-appearance-wide">Lecture topic
          <input maxLength={300} disabled={busy} value={form.topic} onChange={e => setForm(f => ({...f, topic: e.target.value}))} placeholder="Exact approved topic, if known"/>
        </label>
        <label className="studio-appearance-wide">Private participation evidence
          <textarea rows={3} maxLength={5000} disabled={busy} value={form.verification_note} onChange={e => setForm(f => ({...f, verification_note: e.target.value}))} placeholder="Internal evidence supporting previous participation and lecture topic; never publicly displayed"/>
        </label>
        <label>Display order
          <input type="number" min="0" max="999999" disabled={busy} value={form.display_order} onChange={e => setForm(f => ({...f, display_order: e.target.value}))}/>
        </label>
        <label className="studio-appearance-featured"><input type="checkbox" disabled={busy} checked={form.featured} onChange={e => setForm(f => ({...f, featured: e.target.checked}))}/> Feature in lecturer showcase</label>
      </div>
      <div className="studio-appearance-form-footer">
        <small>Saving never verifies or publishes automatically. Those actions require separately authorized staff.</small>
        <button className="studio-appearance-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save for review'}</button>
      </div>
    </form>}
    {loading ? <p className="studio-appearance-muted">Loading lecturer appearances…</p> : data.items.length === 0
      ? <p className="studio-appearance-muted">No appearances recorded yet. Start with an existing lecturer profile.</p>
      : <div className="studio-appearance-list">{data.items.map(item => <article className="studio-appearance-card" key={item.id}>
        <div className="studio-appearance-card-heading">
          <div>
            <strong>{item.lecturer_name}</strong>
            <p>{item.edition_name} · {item.participation_type === 'previous' ? 'Previous lecturer' : 'Upcoming lecturer'}</p>
            {item.topic && <p className="studio-appearance-topic">{item.topic}</p>}
          </div>
          <span className="studio-appearance-state">{item.state}</span>
        </div>
        <div className="studio-appearance-meta">
          <span>{item.verified ? 'Participation verified' : 'Participation not verified'}</span>
          {item.featured && <span>Featured</span>}
        </div>
        <div className="studio-appearance-actions">
          {data.can_edit && <button type="button" disabled={busy} onClick={() => startEdit(item)}>Edit</button>}
          {data.can_verify && !item.verified && item.confirmation_status !== 'declined' &&
            <button type="button" disabled={busy || !item.verification_note?.trim()} title={item.verification_note?.trim() ? '' : 'Save private participation evidence before verifying'} onClick={() => act(item, 'verify')}>Verify evidence</button>}
          {data.can_publish && item.state !== 'published' && item.confirmation_status !== 'declined' &&
            <button type="button" disabled={busy} onClick={() => act(item, 'publish')}>Publish</button>}
          {data.can_publish && item.state === 'published' &&
            <button type="button" disabled={busy} onClick={() => act(item, 'withdraw')}>Withdraw</button>}
        </div>
      </article>)}</div>}
    <div className="studio-appearance-pager">
      <button type="button" disabled={busy || loading || page <= 1} onClick={() => refresh(page-1)}>Previous</button>
      <span>Page {page}</span>
      <button type="button" disabled={busy || loading || !data.has_more} onClick={() => refresh(page+1)}>Next</button>
    </div>
    <p className="studio-appearance-footnote">Historical lecture topics appear on the public DIC page only after recorded verification. To create a new lecturer identity or upload their portrait, use Lecturer profiles first.</p>
  </section>
}
