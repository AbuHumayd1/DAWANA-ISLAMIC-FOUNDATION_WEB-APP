import { useCallback, useEffect, useState } from 'react'
import { backendUrl } from '../services/productionContract'
import {
  studioLecturerAppearances, studioAddSimpleLecturer, studioUpdateSimpleLecturer,
  studioDeleteSimpleLecturer, studioActOnLecturerAppearance,
} from '../services/mediaStudioApi'
import './StudioLecturerAppearances.css'

function friendlyError(error) {
  const message = error?.message || ''
  if (/request failed \(400\)|server could not complete the request \(400\)/i.test(message)) {
    return 'Please check the selected flyer and required fields, then try again.'
  }
  if (/403|permission/i.test(message)) return 'Your account needs permission to manage lecturers. Contact the administrator.'
  if (/failed to fetch|load failed|network/i.test(message)) return 'Could not connect. Check your internet connection and try again.'
  return message || 'The change could not be completed. Please try again.'
}

export default function StudioLecturerAppearances({ onUpdated }) {
  const [data, setData] = useState({ items: [], editions: [] })
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(null)
  const [formOpen, setFormOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [form, setForm] = useState({ name: '', biography: '', edition: '', participation_type: 'previous', flyer: null })
  const refresh = useCallback(async (target = 1) => {
    setLoading(true)
    try {
      const value = await studioLecturerAppearances(target)
      setData(value)
      setPage(target)
    } catch (error) { setMessage(friendlyError(error)) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  function add() {
    setEditing(null)
    setForm({ name: '', biography: '', edition: String(data.editions[0]?.id || ''),
      participation_type: 'previous', flyer: null })
    setMessage('')
    setFormOpen(true)
  }
  function edit(item) {
    setEditing(item)
    setForm({ name: item.lecturer_name === 'Lecturer' ? '' : item.lecturer_name,
      biography: item.biography || '', edition: String(item.edition),
      participation_type: item.participation_type, flyer: null })
    setMessage('')
    setFormOpen(true)
  }
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    if (!editing && !form.flyer) {
      setMessage('Choose a lecturer flyer or photograph before publishing.')
      return
    }
    if (!editing && !form.edition) {
      setMessage('Choose the camp year.')
      return
    }
    setBusy(true)
    setMessage('')
    try {
      if (editing) {
        await studioUpdateSimpleLecturer(editing.id, {
          ...(form.name.trim() ? { name: form.name.trim() } : {}),
          biography: form.biography,
          ...(form.flyer ? { flyer: form.flyer } : {}),
        })
        setMessage('Lecturer updated and published.')
      } else {
        await studioAddSimpleLecturer({
          name: form.name.trim(), biography: form.biography.trim(), edition: form.edition,
          participation_type: form.participation_type, flyer: form.flyer,
        })
        setMessage('Lecturer published successfully.')
      }
      setFormOpen(false)
      onUpdated?.()
      await refresh(1)
    } catch (error) { setMessage(friendlyError(error)) }
    finally { setBusy(false) }
  }
  async function act(item, action) {
    if (busy) return
    if (action === 'delete' && !window.confirm(
      'Permanently delete this lecturer from the showcase? This cannot be undone. Use Withdraw if you only want to hide the lecturer.'
    )) return
    setBusy(true)
    setMessage('')
    try {
      if (action === 'delete') await studioDeleteSimpleLecturer(item.id)
      else await studioActOnLecturerAppearance(item.id, action)
      setMessage(action === 'delete' ? 'Lecturer deleted.' :
        action === 'withdraw' ? 'Lecturer withdrawn from the public showcase.' : 'Lecturer published.')
      onUpdated?.()
      await refresh(page)
    } catch (error) { setMessage(friendlyError(error)) }
    finally { setBusy(false) }
  }

  return <section className="studio-appearance-workflow" aria-label="Lecturers">
    <div className="studio-appearance-workflow-head">
      <h3>Lecturers</h3>
      {data.can_create && <button className="studio-appearance-primary" type="button" disabled={busy} onClick={add}>+ Add lecturer</button>}
    </div>
    {message && <p className="studio-appearance-message" role="status">{message}</p>}
    {formOpen && <form className="studio-appearance-form" onSubmit={submit}>
      <div className="studio-appearance-form-header">
        <strong>{editing ? 'Edit lecturer' : 'Add lecturer'}</strong>
        <button type="button" disabled={busy} aria-label="Close form" onClick={() => setFormOpen(false)}>✕</button>
      </div>
      <div className="studio-appearance-fields">
        <label className="studio-appearance-wide">Lecturer flyer or photograph {editing ? '(optional replacement)' : '*'}
          <input type="file" accept="image/jpeg,image/png,image/webp" required={!editing} disabled={busy}
            onChange={event => setForm(current => ({ ...current, flyer: event.target.files?.[0] || null }))}/>
        </label>
        <label>Lecturer name (optional)
          <input maxLength={200} disabled={busy} value={form.name}
            placeholder="Already printed on the flyer? You can skip this."
            onChange={event => setForm(current => ({ ...current, name: event.target.value }))}/>
        </label>
        {!editing && <><label>Camp year
          <select required disabled={busy} value={form.edition}
            onChange={event => setForm(current => ({ ...current, edition: event.target.value }))}>
            {data.editions.length === 0 && <option value="">No camp year available</option>}
            {data.editions.map(edition => <option key={edition.id} value={edition.id}>{edition.year}</option>)}
          </select>
        </label>
        <label>Showcase
          <select disabled={busy} value={form.participation_type}
            onChange={event => setForm(current => ({ ...current, participation_type: event.target.value }))}>
            <option value="previous">Former lecturers</option>
            <option value="upcoming">Upcoming lecturers</option>
          </select>
        </label></>}
        <label className="studio-appearance-wide">Biography (optional)
          <textarea rows={3} maxLength={2000} disabled={busy} value={form.biography}
            onChange={event => setForm(current => ({ ...current, biography: event.target.value }))}/>
        </label>
      </div>
      <div className="studio-appearance-form-footer">
        <button className="studio-appearance-primary" type="submit" disabled={busy}>
          {busy ? 'Publishing…' : editing ? 'Save and publish' : 'Publish lecturer'}
        </button>
      </div>
    </form>}
    {loading ? <p className="studio-appearance-muted">Loading lecturers…</p> :
      data.items.length === 0 ? <p className="studio-appearance-muted">No lecturers yet. Upload a flyer to add one.</p> :
        <div className="studio-appearance-list">{data.items.map(item =>
          <article className="studio-appearance-card" key={item.id}>
            {item.image_url && <img className="studio-lecturer-thumb" loading="lazy" src={backendUrl(item.image_url)}
              alt={item.lecturer_name || 'Lecturer flyer'}/>}
            <div className="studio-appearance-card-heading">
              <div><strong>{item.lecturer_name}</strong><p>{item.edition_name}</p></div>
              <span className="studio-appearance-state">{item.state === 'published' ? 'Published' : 'Not published'}</span>
            </div>
            <div className="studio-appearance-actions">
              {data.can_edit && <button type="button" disabled={busy} onClick={() => edit(item)}>Edit</button>}
              {data.can_publish && <button type="button" disabled={busy}
                onClick={() => act(item, item.state === 'published' ? 'withdraw' : 'publish')}>
                {item.state === 'published' ? 'Withdraw' : 'Republish'}
              </button>}
              {data.can_delete && <button type="button" className="studio-delete-draft" disabled={busy}
                onClick={() => act(item, 'delete')}>Delete</button>}
            </div>
          </article>)}</div>}
    <div className="studio-appearance-pager">
      <button type="button" disabled={busy || loading || page <= 1} onClick={() => refresh(page - 1)}>Previous</button>
      <span>Page {page}</span>
      <button type="button" disabled={busy || loading || !data.has_more} onClick={() => refresh(page + 1)}>Next</button>
    </div>
  </section>
}
