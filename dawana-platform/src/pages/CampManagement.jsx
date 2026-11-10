import { useEffect, useId, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getOperationsData, postOperationsData } from '../services/operationsApi'
import { assignmentPayload, draftPayload, localDateTime, managementPath } from '../services/campManagement'
import './CampManagement.css'

function useResource(path) {
  const [state, setState] = useState({ path: '', data: null, error: '' }), [revision, reload] = useState(0)
  const key = `${path}:${revision}`
  useEffect(() => {
    if (!path) return undefined
    const controller = new AbortController()
    getOperationsData(path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ path: key, data, error: '' })
    }).catch(error => { if (!controller.signal.aborted) setState({ path: key, data: null, error: error.message }) })
    return () => controller.abort()
  }, [key, path])
  return { data: state.path === key ? state.data : null, error: state.path === key ? state.error : '', reload: () => reload(value => value + 1) }
}

function useMutation(onSaved) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('')
  const pending = useRef(false), transport = useRef(null)
  useEffect(() => {
    const controller = new AbortController(); transport.current = controller
    return () => controller.abort()
  }, [])
  async function save(path, payload) {
    if (pending.current) return false
    pending.current = true; setBusy(true); setMessage(''); setError('')
    try {
      await postOperationsData(path, payload, { signal: transport.current?.signal })
      if (transport.current?.signal.aborted) return false
      setMessage('Change saved. Reloading records…'); onSaved(); return true
    } catch (failure) {
      if (!transport.current?.signal.aborted) setError(failure.message || 'The change could not be saved.')
      return false
    } finally {
      pending.current = false
      if (!transport.current?.signal.aborted) setBusy(false)
    }
  }
  return { save, busy, message, error }
}

function Status({ resource }) {
  return resource.error ? <p role="alert">{resource.error} <button type="button" onClick={resource.reload}>Retry</button></p>
    : !resource.data ? <p role="status">Loading camp records…</p> : null
}

export function ManagementPager({ data, onPage }) {
  return data && data.pages > 1 ? <nav className="cm-pager" aria-label="Record pages"><button type="button" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Previous</button><span>Page {data.page} of {data.pages} · {data.count} records</span><button type="button" disabled={data.page >= data.pages} onClick={() => onPage(data.page + 1)}>Next</button></nav> : null
}

function ManagementShell({ title, children }) {
  const [params, setParams] = useSearchParams()
  const edition = params.get('edition') || ''
  const options = useResource('/camp-management/options/')
  return <section className="cm-page"><div className="ops-page-heading"><div><span className="ops-eyebrow">Camp administration</span><h1>{title}</h1></div></div>
    <section className="ops-panel"><label className="cm-field">Camp edition<select value={edition} onChange={event => setParams(event.target.value ? { edition: event.target.value } : {})}><option value="">Choose a camp edition</option>{options.data?.editions.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><Status resource={options} />
      {!edition && <p>Choose an edition before viewing or changing records.</p>}
      {options.data && !options.data.editions.length && <p>No camp editions are configured. Edition setup requires an authorized configuration workflow.</p>}
      {edition && options.data && !options.data.editions.some(row => String(row.id) === edition) && <p role="alert">This edition is unavailable. Choose one from the list.</p>}
    </section>
    {edition && options.data?.editions.some(row => String(row.id) === edition) && children(edition)}
  </section>
}

export function ClassesOperations() {
  return <ManagementShell title="Classes">{edition => <ClassWorkspace key={edition} edition={edition} />}</ManagementShell>
}

export function ClassEditor({ row, busy, onSave, onCancel }) {
  const id = useId(), [name, setName] = useState(row?.name || ''), [active, setActive] = useState(row?.active ?? true)
  return <form className="ops-panel cm-form" onSubmit={event => { event.preventDefault(); onSave({ name: name.trim(), active, ...(row ? { version: row.version } : {}) }) }}>
    <h2>{row ? 'Edit class' : 'Create class'}</h2><fieldset disabled={busy}><label htmlFor={`${id}-name`}>Class name</label><input id={`${id}-name`} required maxLength={120} value={name} onChange={event => setName(event.target.value)} />
      <label className="cm-check"><input type="checkbox" checked={active} onChange={event => setActive(event.target.checked)} />Active class</label>
      {row?.active && !active && <div><p>Deactivation hides this class from camper projections. Assignments and history are retained.</p><label className="cm-check"><input type="checkbox" required />I confirm this deactivation.</label></div>}
      <div className="cm-actions"><button type="submit">{busy ? 'Saving…' : 'Save class'}</button><button type="button" onClick={onCancel}>Cancel</button></div>
    </fieldset>
  </form>
}

export function AssignmentEditor({ camper, target, busy, onSave, onCancel }) {
  const [reason, setReason] = useState(''), [error, setError] = useState('')
  const transfer = Boolean(camper.assignment)
  return <form className="ops-panel cm-form" onSubmit={event => {
    event.preventDefault(); setError('')
    try { onSave(assignmentPayload(camper, target, reason)) } catch (failure) { setError(failure.message) }
  }}><h2>{transfer ? 'Review class transfer' : 'Review class assignment'}</h2><p>{camper.name}: {camper.assignment?.class_name || 'Unassigned'} → {target.name}</p>
    <fieldset disabled={busy}><label className="cm-field">Reason<textarea required maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <p>The existing registration rule allows registered non-tutor campers. This action does not grant payment, check-in, housing or ID eligibility.</p>
      <label className="cm-check"><input type="checkbox" required />I confirm the camper, edition and destination class.</label>
      <div className="cm-actions"><button type="submit">{busy ? 'Saving…' : transfer ? 'Confirm transfer' : 'Confirm assignment'}</button><button type="button" onClick={onCancel}>Cancel</button></div></fieldset>{error && <p role="alert">{error}</p>}
  </form>
}

function ClassWorkspace({ edition }) {
  const [filters, setFilters] = useState({ q: '', active: '', page: 1 }), [peopleFilters, setPeopleFilters] = useState({ q: '', assignment_state: '', academic_class: '', page: 1 })
  const [editor, setEditor] = useState(null), [target, setTarget] = useState(null), [camper, setCamper] = useState(null)
  const classes = useResource(managementPath('/classes/', edition, filters)), people = useResource(managementPath('/class-assignments/', edition, peopleFilters))
  const mutation = useMutation(() => { classes.reload(); people.reload(); setEditor(null); setCamper(null); setTarget(null) })
  function reload() { setEditor(null); setTarget(null); setCamper(null); classes.reload(); people.reload() }
  return <>
    <section className="ops-panel cm-notice"><h2>Academic classes and campers</h2><p>Class capacity, teacher allocation and assignment ending are not modeled. Existing assignments cannot be deleted here. Transfers retain the assignment record and record before/after history.</p><button type="button" onClick={reload} disabled={mutation.busy}>Reload records / close editors</button></section>
    <div aria-live="polite">{mutation.message && <p role="status">{mutation.message}</p>}{mutation.error && <p role="alert">{mutation.error} Close the editor and reload if the record changed.</p>}</div>
    <section className="ops-panel"><div className="cm-heading"><h2>Classes</h2><button type="button" disabled={mutation.busy} onClick={() => setEditor({ create: true })}>Create class</button></div>
      <form className="cm-filters" onSubmit={event => { event.preventDefault(); const values = new FormData(event.currentTarget); setFilters({ q: values.get('q'), active: values.get('active'), page: 1 }) }}>
        <label>Search classes<input name="q" type="search" maxLength={120} /></label><label>Status<select name="active"><option value="">All classes</option><option value="true">Active</option><option value="false">Inactive</option></select></label><button type="submit">Apply filters</button>
      </form><Status resource={classes} />
      {classes.data && <><div className="cm-table-wrap"><table><caption>Classes in the selected camp edition</caption><thead><tr><th scope="col">Class</th><th scope="col">Status</th><th scope="col">Assigned campers</th><th scope="col">Actions</th></tr></thead><tbody>{classes.data.results.map(row => <tr key={row.id}><th scope="row">{row.name}</th><td>{row.active ? 'Active' : 'Inactive'}</td><td>{row.assigned_count}</td><td><div className="cm-actions"><button type="button" disabled={mutation.busy} onClick={() => setEditor(row)}>Edit {row.name}</button><button type="button" disabled={mutation.busy} onClick={() => { setPeopleFilters(value => ({ ...value, academic_class: row.id, page: 1 })); setCamper(null) }}>View campers</button><button type="button" disabled={!row.active || mutation.busy} aria-pressed={target?.id === row.id} onClick={() => { setTarget(row); setCamper(null) }}>Select destination</button></div></td></tr>)}</tbody></table></div>
        {!classes.data.results.length && <p>No classes match these filters. Create a class or change the search.</p>}<ManagementPager data={classes.data} onPage={page => setFilters(value => ({ ...value, page }))} /></>}
    </section>
    {editor && <ClassEditor key={editor.id ? `${editor.id}:${editor.version}` : 'create'} row={editor.create ? null : editor} busy={mutation.busy} onCancel={() => setEditor(null)} onSave={data => mutation.save(managementPath(editor.id ? `/classes/${editor.id}/` : '/classes/', edition), data)} />}
    <section className="ops-panel"><h2>Camper assignments</h2><p>{target ? `Selected destination: ${target.name}` : 'Select an active destination from the class list before assigning or transferring a camper.'}</p>
      <form className="cm-filters" onSubmit={event => { event.preventDefault(); const values = new FormData(event.currentTarget); setPeopleFilters({ q: values.get('q'), assignment_state: values.get('assignment_state'), academic_class: '', page: 1 }); setCamper(null) }}>
        <label>Search campers<input name="q" type="search" maxLength={200} /></label><label>Assignment status<select name="assignment_state"><option value="">All registered campers</option><option value="unassigned">Without an assignment</option><option value="assigned">Assigned to active class</option><option value="inactive_class">Assignment to inactive class</option></select></label><button type="submit">Apply / clear class filter</button>
      </form>{peopleFilters.academic_class && <p>Filtered to class #{peopleFilters.academic_class}.</p>}<Status resource={people} />
      {people.data && <><ul className="cm-record-list">{people.data.results.map(row => <li key={row.id}><div><strong>{row.name}</strong><p>{row.assignment ? `${row.assignment.class_name}${row.assignment.active ? '' : ' · inactive, not shown in Camper World'}` : 'Not assigned'}</p></div><button type="button" disabled={!target || mutation.busy || row.assignment?.academic_class === target?.id} onClick={() => setCamper(row)}>{row.assignment ? 'Review transfer' : 'Review assignment'}</button></li>)}</ul>{!people.data.results.length && <p>No campers match this edition and these filters.</p>}<ManagementPager data={people.data} onPage={page => setPeopleFilters(value => ({ ...value, page }))} /></>}
    </section>
    {camper && target && <AssignmentEditor key={`${camper.id}:${target.id}`} camper={camper} target={target} busy={mutation.busy} onCancel={() => setCamper(null)} onSave={data => mutation.save(managementPath('/class-assignments/', edition), data)} />}
    <ManagementHistory key={`classes:${edition}`} edition={edition} domain="classes" />
  </>
}

export function AnnouncementPreview({ title, body }) {
  return <section className="cm-preview" aria-label="Announcement content preview"><h3>{title || 'Untitled announcement'}</h3><p>{body || 'No content yet.'}</p><small>Preview only. Saving a draft does not publish it.</small></section>
}

export function AnnouncementEditor({ row, busy, onSave, onCancel }) {
  const [values, setValues] = useState({ title: row?.title || '', body: row?.body || '', starts_at: localDateTime(row?.starts_at), ends_at: localDateTime(row?.ends_at) }), [error, setError] = useState('')
  const update = key => event => setValues(current => ({ ...current, [key]: event.target.value }))
  return <form className="ops-panel cm-form" onSubmit={event => {
    event.preventDefault(); setError('')
    try { onSave(draftPayload(values, row)) } catch (failure) { setError(failure.message) }
  }}><h2>{row ? 'Edit announcement draft' : 'Create announcement draft'}</h2><fieldset disabled={busy}>
    <label className="cm-field">Title<input required maxLength={160} value={values.title} onChange={update('title')} /></label>
    <label className="cm-field">Content<textarea required rows={6} maxLength={5000} value={values.body} onChange={update('body')} /></label>
    <p>Visibility times use your device’s local timezone and are sent with an explicit UTC offset. Leave blank for no time limit. Publication permission is still required.</p>
    <div className="cm-filters"><label>Visible from<input type="datetime-local" step="1" value={values.starts_at} onChange={update('starts_at')} /></label><label>Visible until<input type="datetime-local" step="1" value={values.ends_at} onChange={update('ends_at')} /></label></div>
    <AnnouncementPreview title={values.title} body={values.body} /><div className="cm-actions"><button type="submit">{busy ? 'Saving…' : 'Save draft'}</button><button type="button" onClick={onCancel}>Cancel</button></div></fieldset>{error && <p role="alert">{error}</p>}
  </form>
}

export function PublicationEditor({ row, busy, onSave, onCancel }) {
  const [reason, setReason] = useState('')
  const action = row.status === 'draft' ? 'publish' : 'withdraw'
  return <form className="ops-panel cm-form" onSubmit={event => { event.preventDefault(); onSave({ action, version: row.version, reason: reason.trim() }) }}>
    <h2>{action === 'publish' ? 'Review publication' : 'Review withdrawal'}</h2><AnnouncementPreview title={row.title} body={row.body} />
    <p>Visible from: {row.starts_at ? new Date(row.starts_at).toLocaleString() : 'No start limit'} · Visible until: {row.ends_at ? new Date(row.ends_at).toLocaleString() : 'No end limit'}</p>
    <p>{action === 'publish' ? 'Publishing exposes this announcement to authorized campers and guardians in this edition during its visibility window.' : 'Withdrawal returns this announcement to draft and removes it from camper updates. It does not delete the content or audit history.'}</p>
    <fieldset disabled={busy}><label className="cm-field">Reason<textarea required maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label><label className="cm-check"><input type="checkbox" required />I confirm this {action === 'publish' ? 'publication' : 'withdrawal'} and the selected edition.</label><div className="cm-actions"><button type="submit">{busy ? 'Saving…' : action === 'publish' ? 'Confirm publication' : 'Confirm withdrawal'}</button><button type="button" onClick={onCancel}>Cancel</button></div></fieldset>
  </form>
}

export function AnnouncementsOperations({ user }) {
  return <ManagementShell title="Announcements">{edition => <AnnouncementWorkspace key={edition} edition={edition} user={user} />}</ManagementShell>
}

function AnnouncementWorkspace({ edition, user }) {
  const [filters, setFilters] = useState({ q: '', status: '', audience: '', page: 1 }), [editor, setEditor] = useState(null), [publication, setPublication] = useState(null), [preview, setPreview] = useState(null)
  const resource = useResource(managementPath('/announcements/', edition, filters))
  const mutation = useMutation(() => { resource.reload(); setEditor(null); setPublication(null); setPreview(null) })
  function reload() { setEditor(null); setPublication(null); setPreview(null); resource.reload() }
  return <>
    <section className="ops-panel"><p>Audience: authorized campers and guardians in the selected edition. Custom audiences, approval-submission stages and content-version restoration are not modeled. Drafts remain private to authorized announcement staff.</p><button type="button" onClick={reload} disabled={mutation.busy}>Reload records / close editors</button></section>
    <div aria-live="polite">{mutation.message && <p role="status">{mutation.message}</p>}{mutation.error && <p role="alert">{mutation.error} Close the editor and reload if the record changed.</p>}</div>
    <section className="ops-panel"><div className="cm-heading"><h2>Edition announcements</h2>{user.permissions.edit_announcements && <button type="button" disabled={mutation.busy} onClick={() => setEditor({ create: true })}>Create draft</button>}</div>
      <form className="cm-filters" onSubmit={event => { event.preventDefault(); const values = new FormData(event.currentTarget); setFilters({ q: values.get('q'), status: values.get('status'), audience: values.get('audience'), page: 1 }) }}>
        <label>Search announcements<input name="q" type="search" maxLength={160} /></label><label>Publication status<select name="status"><option value="">All states</option><option value="draft">Draft</option><option value="published">Published</option></select></label><label>Audience<select name="audience"><option value="">All supported audiences</option><option value="edition">Selected edition campers and guardians</option></select></label><button type="submit">Apply filters</button>
      </form><Status resource={resource} />
      {resource.data && <><ul className="cm-record-list">{resource.data.results.map(row => <li key={row.id}><div><h3>{row.title}</h3><p>{row.status} · {row.visibility} · edition audience</p><p>From: {row.starts_at ? new Date(row.starts_at).toLocaleString() : 'No start limit'} · Until: {row.ends_at ? new Date(row.ends_at).toLocaleString() : 'No end limit'}</p></div><div className="cm-actions"><button type="button" onClick={() => setPreview(row)}>Preview</button>{row.status === 'draft' && user.permissions.edit_announcements && <button type="button" disabled={mutation.busy} onClick={() => setEditor(row)}>Edit draft</button>}{user.permissions.publish_announcements && <button type="button" disabled={mutation.busy} onClick={() => setPublication(row)}>{row.status === 'draft' ? 'Review publication' : 'Review withdrawal'}</button>}</div></li>)}</ul>{!resource.data.results.length && <p>No announcements match this edition and these filters.</p>}<ManagementPager data={resource.data} onPage={page => setFilters(value => ({ ...value, page }))} /></>}
    </section>
    {preview && <section className="ops-panel"><AnnouncementPreview title={preview.title} body={preview.body} /><button type="button" onClick={() => setPreview(null)}>Close preview</button></section>}
    {editor && <AnnouncementEditor key={editor.id ? `${editor.id}:${editor.version}` : 'create'} row={editor.create ? null : editor} busy={mutation.busy} onCancel={() => setEditor(null)} onSave={data => mutation.save(managementPath(editor.id ? `/announcements/${editor.id}/` : '/announcements/', edition), data)} />}
    {publication && <PublicationEditor key={`${publication.id}:${publication.version}`} row={publication} busy={mutation.busy} onCancel={() => setPublication(null)} onSave={data => mutation.save(managementPath(`/announcements/${publication.id}/publication/`, edition), data)} />}
    <ManagementHistory key={`announcements:${edition}`} domain="announcements" edition={edition} />
  </>
}

function ManagementHistory({ domain, edition }) {
  const [open, setOpen] = useState(false)
  return <section className="ops-panel"><h2>{domain === 'classes' ? 'Class and assignment history' : 'Announcement history'}</h2><button type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Hide history' : 'View history'}</button>{open && <HistoryRows domain={domain} edition={edition} />}</section>
}

function HistoryRows({ domain, edition }) {
  const [page, setPage] = useState(1)
  const resource = useResource(managementPath(`/camp-management/${domain}/history/`, edition, { page }))
  return <><p>History records changes, not restorable content versions. Earlier audit entries may not contain before/after snapshots. Staff identity is shown only with audit permission.</p><button type="button" onClick={resource.reload}>Refresh history</button><Status resource={resource} />
    {resource.data && <><ul className="cm-history">{resource.data.results.map(row => <li key={row.id}><strong>{row.action}</strong><p>{row.target_type} #{row.target_id} · {new Date(row.time).toLocaleString()}{row.actor ? ` · ${row.actor}` : ''}</p>{row.reason && <p>Reason: {row.reason}</p>}<details><summary>Before and after</summary><pre>{JSON.stringify({ before: row.before, after: row.after }, null, 2)}</pre></details></li>)}</ul>{!resource.data.results.length && <p>No recorded changes for this edition.</p>}<ManagementPager data={resource.data} onPage={setPage} /></>}
  </>
}
