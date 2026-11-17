import { useEffect, useState } from 'react'
import { studioAssets, studioLinkAsset, studioAssetMetadata, studioArchiveAsset, studioPlacement } from '../services/mediaStudioApi'
import './StudioDestinations.css'

const destinationNames = {
  foundation_archive: 'Foundation media archive',
  foundation_home: 'Foundation homepage',
  dic_memories: 'DIC memories gallery',
  dic_landing: 'DIC landing page',
  dic_resources: 'DIC lecture resources',
  camper_resources: 'Camper Portal resources',
}
const choices = {
  photos: ['foundation_archive', 'foundation_home', 'dic_memories', 'dic_landing'],
  videos: ['foundation_archive', 'foundation_home', 'dic_landing'],
  hosted: ['foundation_archive', 'foundation_home', 'dic_landing', 'dic_resources'],
  recordings: ['dic_resources', 'camper_resources'],
  flyers: ['foundation_archive', 'dic_landing'],
  promotions: ['foundation_archive', 'foundation_home', 'dic_landing'],
  lecturers: ['foundation_archive', 'dic_landing'],
  activities: ['foundation_archive', 'dic_landing'],
  appearances: ['foundation_archive', 'dic_landing'],
}
const scoped = (dest) => dest.startsWith('dic_') || dest === 'camper_resources'

export default function StudioDestinations({ user, editions, library, sourceLinkRefresh }) {
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [showArchive, setShowArchive] = useState(false)
  const [linkId, setLinkId] = useState('')
  const [linkKind, setLinkKind] = useState(library)
  const [revision, setRevision] = useState(0)
  const [selected, setSelected] = useState('')
  const [destination, setDestination] = useState('foundation_archive')
  const [edition, setEdition] = useState('')
  const [album, setAlbum] = useState('')
  const [campaign, setCampaign] = useState('')
  const [programme, setProgramme] = useState('')
  const [eventName, setEventName] = useState('')
  const [description, setDescription] = useState('')
  const current = items.find(item => item.id === selected)
  const selectedChoices = choices[current?.source_kind] || []
  useEffect(() => {
    if (selectedChoices.length && !selectedChoices.includes(destination)) {
      setDestination(selectedChoices[0])
      setEdition('')
    }
  }, [selected, items, destination])
  useEffect(() => {
    let active = true
    setLoading(true)
    studioAssets(page).then(response => {
      if (!active) return
      setHasMore(Boolean(response.has_more))
      setItems(previous => page === 1 ? (response.assets || []) :
        [...previous.filter(item => !(response.assets || []).some(next => next.id === item.id)), ...(response.assets || [])])
      if (page === 1) setSelected(current => response.assets?.some(item => item.id === current) ? current : '')
    }).catch(error => { if (active) setMessage(error.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [revision, page, sourceLinkRefresh])
  useEffect(() => {
    if (!current) return
    setAlbum(current.album || '')
    setCampaign(current.campaign || '')
    setProgramme(current.programme || '')
    setEventName(current.event || '')
    setDescription(current.description || '')
  }, [current?.id, revision])

  async function run(action) {
    setBusy(true); setMessage('')
    try {
      const response = await action()
      if (response.asset) {
        setItems(previous => {
          const next = previous.filter(row => row.id !== response.asset.id)
          return [response.asset, ...next]
        })
        setSelected(response.asset.id)
      } else {
        setRevision(n => n + 1)
      }
      setMessage('Saved. Publication is controlled independently for each destination.')
    } catch (error) { setMessage(error.message) }
    finally { setBusy(false) }
  }
  async function link(event) {
    event.preventDefault()
    if (!/^[1-9]\d*$/.test(String(linkId))) { setMessage('Choose a valid media ID.'); return }
    await run(() => studioLinkAsset(linkKind, Number(linkId)))
    setLinkId('')
  }
  async function placement(event) {
    event.preventDefault()
    if (!current) return
    if (scoped(destination) && !edition) { setMessage('Choose the exact camp edition.'); return }
    await run(() => studioPlacement(current.id, destination, event.nativeEvent.submitter?.value || 'draft', scoped(destination) ? edition : null))
  }
  return <section className="studio-destinations" aria-labelledby="destinations-heading">
    <header className="studio-destinations-head"><div><span className="studio-kicker">ONE ASSET · MANY DESTINATIONS</span><h2 id="destinations-heading">Foundation publishing</h2><p>Connect existing media once, organize it, and independently choose where its approved content appears.</p></div><span>Private asset catalogue</span></header>
    {message && <p role="status" className="studio-notice">{message}</p>}
    <form className="studio-link" onSubmit={link}><strong>Link an existing media item</strong>
      <label>Collection<select value={linkKind} onChange={e => setLinkKind(e.target.value)}>{Object.keys(choices).filter(x => user.libraries?.includes(x)).map(kind => <option value={kind} key={kind}>{kind}</option>)}</select></label>
      <label>Media ID<input type="number" min="1" required value={linkId} onChange={e => setLinkId(e.target.value)} placeholder="ID from the collection above" /></label>
      <button type="submit" disabled={busy || !linkId}>Add to catalogue</button>
    </form>
    <div className="studio-catalogue-body">
      <div className="studio-linked-list"><div className="studio-linked-title"><strong>Linked media ({items.length})</strong><label><input type="checkbox" checked={showArchive} onChange={e => setShowArchive(e.target.checked)} />Show archived</label></div>
        {loading ? <p>Loading catalogue…</p> : items.filter(x => showArchive || !x.archived).length ? items.filter(x => showArchive || !x.archived).map(item =>
          <button type="button" className={selected === item.id ? 'studio-linked-item selected' : 'studio-linked-item'} key={item.id} onClick={() => setSelected(item.id)}><span>{item.source_kind}</span><strong>{item.title}</strong><small>{item.archived ? 'Archived' : item.destinations?.filter(p => p.state === 'published').length + ' published destinations'}</small></button>)
          : <p className="studio-empty-linked">No assets linked yet. Link an existing media record to organize and distribute it.</p>}
        {!loading && hasMore && <button type="button" className="studio-loadmore" onClick={() => setPage(n => n + 1)}>Load more assets</button>}
      </div>
      <div className="studio-destination-detail">
        {!current ? <div className="studio-destination-empty"><strong>Select a linked asset</strong><p>Its metadata and destination publication controls will appear here.</p></div> : <>
          <div className="studio-destination-asset"><span className="studio-kicker">{current.source_kind.toUpperCase()}</span><h3>{current.title}</h3><p>Asset ID: {current.id}</p></div>
          <form className="studio-catalogue-edit" onSubmit={e => { e.preventDefault();run(() => studioAssetMetadata(current.id,{album,campaign,programme,event:eventName,description})) }}>
            <strong>Organize this asset</strong><div className="studio-catalogue-fields"><label>Album<input maxLength="150" value={album} onChange={e=>setAlbum(e.target.value)}/></label><label>Campaign<input maxLength="150" value={campaign} onChange={e=>setCampaign(e.target.value)}/></label><label>Programme<input maxLength="150" value={programme} onChange={e=>setProgramme(e.target.value)}/></label><label>Event<input maxLength="150" value={eventName} onChange={e=>setEventName(e.target.value)}/></label></div><label>Description<textarea maxLength="5000" value={description} onChange={e=>setDescription(e.target.value)}/></label><button type="submit" disabled={busy}>Save organization</button>
          </form>
          <div className="studio-placements"><h4>Publication destinations</h4>
          {current.destinations?.length ? <div className="studio-placement-tags">{current.destinations.map(p=><div key={p.id} className="studio-placement-tag"><span>{destinationNames[p.destination] || p.destination}{p.edition ? ` · Edition ${p.edition}` : ''}</span><strong>{p.state}</strong></div>)}</div> : <p>No destinations assigned.</p>}
          <form onSubmit={placement} className="studio-placement-editor"><label>Destination<select value={destination} onChange={e=>{setDestination(e.target.value);setEdition('')}}>{selectedChoices.map(value=><option key={value} value={value}>{destinationNames[value]}</option>)}</select></label>
          {scoped(destination) && <label>Camp edition<select value={edition} onChange={e=>setEdition(e.target.value)} required><option value="">Choose edition</option>{editions.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>}
          <div className="studio-placement-buttons"><button type="submit" value="draft" disabled={busy}>Save draft placement</button><button type="submit" value="publish" disabled={busy || current.archived}>Publish destination</button><button type="submit" value="withdraw" disabled={busy}>Withdraw destination</button></div>
          </form><small>Publishing requires the original media item to be approved. Private camper resources remain subject to camper entitlement; a placement cannot bypass it.</small>
          </div>
          <div className="studio-archive-actions"><button type="button" disabled={busy} onClick={()=>run(()=>studioArchiveAsset(current.id,current.archived?'restore':'archive'))}>{current.archived?'Restore to drafts':'Archive and withdraw all destinations'}</button></div>
        </>}
      </div>
    </div>
  </section>
}
