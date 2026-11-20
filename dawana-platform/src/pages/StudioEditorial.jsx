import { useCallback, useEffect, useState } from 'react'
import {
  studioEditorialCollections, studioCreateCollection, studioUpdateCollection,
  studioEditorialItems, studioCreateEditorialItem, studioUpdateEditorialItem, studioPublishEditorialItem,
} from '../services/mediaStudioApi'
import './StudioEditorial.css'

const KINDS = [
  ['article', 'Article or written response'], ['document', 'PDF or research paper'],
  ['event', 'Programme announcement'], ['live', 'Live broadcast / Google Meet'],
  ['podcast', 'Podcast episode'], ['video', 'YouTube or Vimeo recording'],
]
const blank = { kind: 'article', title: '', description: '', body: '', video_url: '',
  meeting_url: '', collection_id: '', event_at: '', season: '1', episode: '1' }
const makeSlug = title => title.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
  .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 170)

export default function StudioEditorial({ user, onCollectionsChange }) {
  const [collections, setCollections] = useState([])
  const [items, setItems] = useState([])
  const [form, setForm] = useState(blank)
  const [newCollection, setNewCollection] = useState({ title: '', kind: 'programme', description: '' })
  const [file, setFile] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [version, setVersion] = useState(0)
  const publisher = user?.owner || user?.can_publish_destinations
  const editor = user?.owner || user?.can_manage_catalogue

  const refresh = useCallback(async () => {
    const [c, p] = await Promise.all([studioEditorialCollections(), studioEditorialItems()])
    setCollections(c.collections || [])
    setItems(p.items || [])
  }, [])
  useEffect(() => {
    if (!editor) return
    let active = true
    setLoading(true)
    Promise.all([studioEditorialCollections(), studioEditorialItems()])
      .then(([c,p]) => { if (active) {setCollections(c.collections || []);setItems(p.items || [])} })
      .catch(e => { if (active) setMessage(e.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [editor, version])

  async function run(operation, success) {
    setBusy(true); setMessage('')
    try {
      await operation()
      await refresh()
      onCollectionsChange?.()
      setMessage(success)
    } catch (error) {
      setMessage(error.message || 'Could not save this editorial change.')
    } finally { setBusy(false) }
  }
  function addCollection(event) {
    event.preventDefault()
    const fields = {...newCollection, slug: makeSlug(newCollection.title)}
    run(() => studioCreateCollection(fields), 'Collection saved. Make it public when you are ready.')
    setNewCollection({title: '', kind: 'programme', description: ''})
  }
  function addPublication(event) {
    event.preventDefault()
    const fields = {...form,
      collection_id: form.collection_id || null,
      event_at: form.event_at ? new Date(form.event_at).toISOString() : null,
    }
    run(async () => {
      if (editingId) await studioUpdateEditorialItem(editingId, fields)
      else await studioCreateEditorialItem(fields, file)
      setForm(blank)
      setFile(null)
      setEditingId(null)
    }, editingId ? 'Draft updated.' : 'Draft saved. Review it below before publishing.')
  }
  const update = (key, value) => setForm(old => ({...old, [key]: value}))
  if (!editor) return null
  return <section className="studio-editorial" aria-label="Foundation Publishing">
    <div className="studio-editorial-heading">
      <div><span className="studio-kicker">FOUNDATION PUBLISHING</span>
        <h2>Collections, podcasts & live programmes</h2>
        <p>Build new lecture series, publish articles, announce live broadcasts and organise podcast episodes. All new items begin as private drafts.</p>
      </div>
    </div>
    {message && <p role="status" className="studio-notice">{message}</p>}
    {loading ? <p>Loading editorial content…</p> : <>
      <details className="studio-editorial-panel">
        <summary>New programme or podcast collection</summary>
        <form onSubmit={addCollection} className="studio-editorial-form">
          <label>Collection name<input required maxLength={160} value={newCollection.title} onChange={e=>setNewCollection(v=>({...v,title:e.target.value}))} placeholder="Youth Podcast, Weekly Lectures…" /></label>
          <label>Collection type<select value={newCollection.kind} onChange={e=>setNewCollection(v=>({...v,kind:e.target.value}))}><option value="programme">Programme / lecture series</option><option value="podcast">Podcast show</option></select></label>
          <label>Short description<textarea maxLength={500} value={newCollection.description} onChange={e=>setNewCollection(v=>({...v,description:e.target.value}))}/></label>
          <button disabled={busy || !makeSlug(newCollection.title)} type="submit">Create collection</button>
        </form>
      </details>
      {collections.length > 0 && <div className="studio-editorial-collections">
        {collections.map(c=><article key={c.id}><strong>{c.title}</strong>
          <small>{c.kind === 'podcast' ? 'Podcast' : 'Lecture / programme'} · {c.is_public ? 'Public' : 'Hidden'}</small>
          {publisher && <button disabled={busy} onClick={()=>run(()=>studioUpdateCollection(c.id,{is_public:!c.is_public}),c.is_public?'Collection hidden from public media.':'Collection visible on public media.')}>{c.is_public?'Hide collection':'Show on Media page'}</button>}
        </article>)}
      </div>}
      <details className="studio-editorial-panel" open>
        <summary>{editingId ? 'Edit draft publication' : 'Create a publication'}</summary>
        <form className="studio-editorial-form" onSubmit={addPublication}>
          <label>Content type<select value={form.kind} onChange={e=>update('kind',e.target.value)}>{KINDS.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
          <label>Publication title<input required value={form.title} maxLength={250} onChange={e=>update('title',e.target.value)}/></label>
          <label>Programme / podcast collection<select value={form.collection_id} onChange={e=>update('collection_id',e.target.value)}><option value="">General publications</option>{collections.filter(c=>form.kind!=='podcast'||c.kind==='podcast').map(c=><option value={c.id} key={c.id}>{c.title}</option>)}</select></label>
          <label>Short description<textarea maxLength={3000} value={form.description} onChange={e=>update('description',e.target.value)} /></label>
          {form.kind==='article' && <label>Article text<textarea rows={8} maxLength={30000} value={form.body} onChange={e=>update('body',e.target.value)} placeholder="Write the article here. Text is displayed as plain paragraphs, not executable HTML." /></label>}
          {['podcast','video','live'].includes(form.kind) && <label>YouTube / Vimeo URL<input type="url" value={form.video_url} onChange={e=>update('video_url',e.target.value)} placeholder="https://www.youtube.com/watch?v=..." /></label>}
          {['live','event'].includes(form.kind) && <label>Google Meet joining link (optional)<input type="url" value={form.meeting_url} onChange={e=>update('meeting_url',e.target.value)} placeholder="https://meet.google.com/..." /></label>}
          {['live','event'].includes(form.kind) && <label>Scheduled time<input type="datetime-local" value={form.event_at} onChange={e=>update('event_at',e.target.value)}/></label>}
          {form.kind==='podcast' && <div className="studio-editorial-numbers"><label>Season<input type="number" min="1" max="999" value={form.season} onChange={e=>update('season',e.target.value)}/></label><label>Episode<input type="number" min="1" max="999" value={form.episode} onChange={e=>update('episode',e.target.value)}/></label></div>}
          {form.kind==='document' && <label>PDF file (max 15 MB)<input type="file" accept="application/pdf,.pdf" onChange={e=>setFile(e.target.files?.[0] || null)}/></label>}
          <button disabled={busy}>{editingId ? 'Save draft changes' : 'Save private draft'}</button>{editingId && <button type="button" disabled={busy} onClick={()=>{setEditingId(null);setForm(blank);setFile(null)}}>Cancel editing</button>}
        </form>
      </details>
      <section className="studio-editorial-panel">
        <h3>Drafts and published items</h3>
        {!items.length ? <p>No editorial publications yet.</p> :
          <div className="studio-editorial-items">{items.map(item=><article key={item.id}>
            <div><strong>{item.title}</strong><small>{item.kind}{item.kind==='podcast'?' · Season '+item.season+' / Episode '+item.episode:''} · {item.state}</small></div>
            <div className="studio-editorial-actions">
              {item.state !== 'published' && <button disabled={busy} type="button" onClick={()=>{setEditingId(item.id);setForm({...blank,kind:item.kind,title:item.title,description:item.description,body:item.body,video_url:item.video_url,meeting_url:item.meeting_url,live_state:item.live_state,season:String(item.season),episode:String(item.episode),collection_id:item.collection_id || '',event_at:item.event_at ? new Date(new Date(item.event_at).getTime() - new Date(item.event_at).getTimezoneOffset()*60000).toISOString().slice(0,16):''});setFile(null)}}>Edit draft</button>}
              {publisher && <button disabled={busy} type="button" onClick={()=>run(()=>studioPublishEditorialItem(item.id,item.state==='published'?'withdraw':'publish'), item.state==='published'?'Publication withdrawn.':'Publication published to the Media page.')}>{item.state==='published'?'Withdraw':'Publish'}</button>}
              {publisher && item.kind === 'live' && item.state === 'published' && <button disabled={busy || item.live_state === 'ended'} type="button" onClick={()=>run(()=>studioPublishEditorialItem(item.id,item.live_state==='live'?'end_live':'go_live'),'Live broadcast status updated.')}>{item.live_state==='live'?'End live':'Go live'}</button>}
              {publisher && item.state === 'published' && !item.notification_sent && <button disabled={busy} type="button" onClick={()=>run(()=>studioPublishEditorialItem(item.id,'notify'),'Notification request checked. See provider configuration for delivery status.')}>Notify subscribers</button>}
            </div>
          </article>)}</div>}
      </section>
    </>}
  </section>
}
