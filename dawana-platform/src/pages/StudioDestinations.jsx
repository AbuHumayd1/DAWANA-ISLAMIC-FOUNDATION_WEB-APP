import { useEffect, useRef, useState } from 'react'
import { studioAssets, studioLinkAsset, studioAssetMetadata, studioArchiveAsset, studioPlacement } from '../services/mediaStudioApi'
import './StudioDestinations.css'

const destinationNames = {
  foundation_archive: 'Media page — collections',
  foundation_home: 'Homepage — latest 3 featured media',
  dic_memories: 'DIC memories gallery',
  dic_landing: 'DIC landing page',
  dic_resources: 'DIC lecture resources',
  camper_resources: 'Camper Portal — private lecture audio',
}
const choices = {
  photos: ['foundation_archive', 'foundation_home', 'dic_memories', 'dic_landing'],
  videos: ['foundation_archive', 'foundation_home', 'dic_landing'],
  hosted: ['foundation_archive', 'foundation_home', 'dic_landing', 'dic_resources'],
  recordings: ['foundation_archive', 'camper_resources'],
  flyers: ['foundation_archive'],
  promotions: ['foundation_archive', 'foundation_home', 'dic_landing'],
  lecturers: ['foundation_archive', 'dic_landing'],
  activities: ['foundation_archive', 'dic_landing'],
  appearances: ['foundation_archive', 'dic_landing'],
}
const scoped = (dest) => dest.startsWith('dic_') || dest === 'camper_resources'

export default function StudioDestinations({ user, editions, library, sourceLinkRefresh, focusAsset }) {
  const handledFocus = useRef('')
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [showArchive, setShowArchive] = useState(false)
  const [catalogueSearch, setCatalogueSearch] = useState('')
  const [collectionFilter, setCollectionFilter] = useState('')
  const [albumFilter, setAlbumFilter] = useState('')
  const [availableAlbums, setAvailableAlbums] = useState([])
  const [batchIds, setBatchIds] = useState([])
  const [batchDestination, setBatchDestination] = useState('')
  const [batchEdition, setBatchEdition] = useState('')
  const [batchAction, setBatchAction] = useState('publish')
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
  const filteredItems = items.filter(item => showArchive || !item.archived)
  const selectedChoices = choices[current?.source_kind] || []
  const batchAssets = items.filter(item => batchIds.includes(item.id))
  const batchKind = batchAssets[0]?.source_kind
  const batchChoices = choices[batchKind] || []
  useEffect(() => {
    if (selectedChoices.length && !selectedChoices.includes(destination)) {
      setDestination(selectedChoices[0])
      setEdition('')
    }
  }, [selected, items, destination])
  useEffect(() => {
    let active = true
    setLoading(true)
    studioAssets(page, { kind: collectionFilter, q: catalogueSearch, album: albumFilter }).then(response => {
      if (!active) return
      setHasMore(Boolean(response.has_more))
      setAvailableAlbums(response.albums || [])
      setItems(previous => page === 1 ? (response.assets || []) :
        [...previous.filter(item => !(response.assets || []).some(next => next.id === item.id)), ...(response.assets || [])])
      if (page === 1) setSelected(current => response.assets?.some(item => item.id === current) ? current : '')
    }).catch(error => { if (active) setMessage(error.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [revision, page, sourceLinkRefresh, collectionFilter, catalogueSearch, albumFilter])
  useEffect(() => {
    if (focusAsset && focusAsset !== handledFocus.current && items.some(item => item.id === focusAsset)) {
      handledFocus.current = focusAsset
      setSelected(focusAsset)
    }
  }, [focusAsset, items])
  useEffect(() => { if (choices[library]) setLinkKind(library) }, [library])
  useEffect(() => {
    if (batchChoices.length && !batchChoices.includes(batchDestination)) {
      setBatchDestination(batchChoices[0]); setBatchEdition('')
    }
  }, [batchKind, batchDestination])
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
  function toggleBatch(item, enabled) {
    setBatchIds(previous => {
      if (!enabled) return previous.filter(id => id !== item.id)
      const first = items.find(row => row.id === previous[0])
      if (first && first.source_kind !== item.source_kind) return previous
      if (previous.length >= 20) { setMessage('Bulk actions are limited to 20 assets per batch.'); return previous }
      return [...previous, item.id]
    })
  }
  async function applyBatch(event) {
    event.preventDefault()
    if (!user.can_publish_destinations || !batchAssets.length || batchAssets.length > 20) return
    if (scoped(batchDestination) && !batchEdition) { setMessage('Choose a camp edition for this batch.'); return }
    setBusy(true); setMessage('')
    let completed = 0
    const failures = []
    for (const asset of batchAssets) {
      try {
        await studioPlacement(asset.id, batchDestination, batchAction,
          scoped(batchDestination) ? batchEdition : null)
        completed++
      } catch (error) { failures.push(`${asset.title}: ${error.message}`) }
    }
    setBatchIds([])
    setRevision(n => n + 1)
    setMessage(`${completed}/${batchAssets.length} assets ${batchAction === 'publish' ? 'published' : 'withdrawn'} for the selected destination.${failures.length ? ' Unchanged: ' + failures.slice(0, 5).join('; ') + (failures.length > 5 ? '; and additional failures' : '') : ''}`)
    setBusy(false)
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
  return <section id="studio-publishing" className="studio-destinations" aria-labelledby="destinations-heading">
    <header className="studio-destinations-head"><div><span className="studio-kicker">ONE ASSET · MANY DESTINATIONS</span><h2 id="destinations-heading">Foundation publishing</h2><p>Connect existing media once, organize it, and independently choose where its approved content appears.</p></div><span>Private asset catalogue</span></header>
    {message && <p role="status" className="studio-notice">{message}</p>}
    {!items.length && !loading && !catalogueSearch && !collectionFilter && !albumFilter && <div className="studio-publishing-onboarding"><strong>No media ready to place yet</strong><p>Choose a collection above, add or select an item, then use “Add to Foundation catalogue” on that item. After linking it, choose where it should appear on the website. You do not need to enter an ID manually for the usual workflow.</p></div>}
    <details className="studio-advanced-link"><summary>Advanced: link an existing item by ID</summary>
      <p>Only use this when you already know the item’s record ID. For most media, use the button on the item in its collection instead.</p>
      <form className="studio-link" onSubmit={link}><strong>Existing media record</strong>
        <label>Collection<select value={linkKind} onChange={e => setLinkKind(e.target.value)}>{Object.keys(choices).filter(x => user.libraries?.includes(x)).map(kind => <option value={kind} key={kind}>{kind}</option>)}</select></label>
        <label>Media ID<input type="number" min="1" required value={linkId} onChange={e => setLinkId(e.target.value)} placeholder="Record ID" /></label>
        <button type="submit" disabled={busy || !linkId}>Link item</button>
      </form>
    </details>
    <div className="studio-catalogue-body">
      <div className="studio-linked-list"><div className="studio-linked-title"><strong>Linked media ({items.length})</strong><label><input type="checkbox" checked={showArchive} onChange={e => setShowArchive(e.target.checked)} />Show archived</label></div>
        <div className="studio-catalogue-filters"><label className="studio-catalogue-search"><span>Collection</span><select aria-label="Filter catalogue collection" value={collectionFilter} onChange={event => {setPage(1);setBatchIds([]);setCollectionFilter(event.target.value);setAlbumFilter('')}}><option value="">All permitted collections</option>{Object.keys(choices).filter(x=>user.libraries?.includes(x)).map(kind=><option key={kind} value={kind}>{kind}</option>)}</select></label><label className="studio-catalogue-search"><span>Search entire catalogue</span><input type="search" aria-label="Search full catalogue" placeholder="Title, album or programme…" maxLength="100" value={catalogueSearch} onChange={event => {setPage(1);setBatchIds([]);setCatalogueSearch(event.target.value)}} /></label>{collectionFilter === 'photos' && <label className="studio-catalogue-search"><span>Photo album</span><select aria-label="Filter photography by album" value={albumFilter} onChange={event => {setPage(1);setBatchIds([]);setAlbumFilter(event.target.value)}}><option value="">All albums</option>{availableAlbums.map(name=><option key={name} value={name}>{name}</option>)}</select></label>}</div>
        {loading && page === 1 ? <p>Loading catalogue…</p> : filteredItems.length ? filteredItems.map(item =>
          <div key={item.id} className="studio-linked-row">{user.can_publish_destinations && <input type="checkbox" aria-label={`Select ${item.title} for bulk publication`} checked={batchIds.includes(item.id)} disabled={busy || (batchKind && batchKind !== item.source_kind && !batchIds.includes(item.id))} onChange={event => toggleBatch(item, event.target.checked)} />}<button type="button" className={selected === item.id ? 'studio-linked-item selected' : 'studio-linked-item'} onClick={() => setSelected(item.id)}><span>{item.source_kind}{item.album ? ` · ${item.album}` : ''}</span><strong>{item.title}</strong><small>{item.archived ? 'Archived' : item.destinations?.filter(p => p.state === 'published').length + ' published destinations'}</small></button></div>)
          : <p className="studio-empty-linked">No assets linked yet. Link an existing media record to organize and distribute it.</p>}
        {!loading && hasMore && <button type="button" className="studio-loadmore" onClick={() => setPage(n => n + 1)}>Load more assets</button>}
        {user.can_publish_destinations && batchIds.length > 0 && <form className="studio-bulk-actions" onSubmit={applyBatch}><strong>Batch destination action · {batchIds.length} selected {batchKind}</strong><p>Only assets in the same collection can be selected. Each source must already be published. Failed items stay unchanged and are reported individually; there is no automatic retry.</p><label>Destination<select value={batchDestination} onChange={event => {setBatchDestination(event.target.value);setBatchEdition('')}}>{batchChoices.map(value=><option value={value} key={value}>{destinationNames[value]}</option>)}</select></label>{scoped(batchDestination) && <label>Edition<select required value={batchEdition} onChange={event => setBatchEdition(event.target.value)}><option value="">Choose edition</option>{editions.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>}<label>Action<select value={batchAction} onChange={event => setBatchAction(event.target.value)}><option value="publish">Publish destination</option><option value="withdraw">Withdraw destination</option></select></label><button disabled={busy || !batchDestination} type="submit">{busy ? 'Processing assets…' : `Apply ${batchAction} to ${batchIds.length} selected`}</button><button type="button" disabled={busy} onClick={() => setBatchIds([])}>Clear selection</button></form>}
      </div>
      <div className="studio-destination-detail">
        {!current ? <div className="studio-destination-empty"><strong>Select a linked asset</strong><p>Its metadata and destination publication controls will appear here.</p></div> : <>
          <div className="studio-destination-asset"><span className="studio-kicker">{current.source_kind.toUpperCase()} · PUBLISHING STUDIO</span><h3>{current.title}</h3><p>Catalogue reference: {current.id}</p><p className="studio-asset-publishing-hint">Step 1: publish the original media in its library. Step 2: select where it should appear below. You can withdraw any destination without affecting others.</p></div>
          <form className="studio-catalogue-edit" onSubmit={e => { e.preventDefault();run(() => studioAssetMetadata(current.id,{album,campaign,programme,event:eventName,description})) }}>
            <strong>Organize this asset</strong><div className="studio-catalogue-fields"><label>Album<input maxLength="150" value={album} onChange={e=>setAlbum(e.target.value)}/></label><label>Campaign<input maxLength="150" value={campaign} onChange={e=>setCampaign(e.target.value)}/></label><label>Programme<input maxLength="150" value={programme} onChange={e=>setProgramme(e.target.value)}/></label><label>Event<input maxLength="150" value={eventName} onChange={e=>setEventName(e.target.value)}/></label></div><label>Description<textarea maxLength="5000" value={description} onChange={e=>setDescription(e.target.value)}/></label><button type="submit" disabled={busy}>Save organization</button>
          </form>
          <div className="studio-placements"><h4>Publication destinations</h4>
          {current.destinations?.length ? <div className="studio-placement-tags">{current.destinations.map(p=><div key={p.id} className="studio-placement-tag"><span>{destinationNames[p.destination] || p.destination}{p.edition ? ` · Edition ${p.edition}` : ''}</span><strong>{p.state}</strong></div>)}</div> : <p>No destinations assigned.</p>}
          <form onSubmit={placement} className="studio-placement-editor"><label>Destination<select value={destination} onChange={e=>{setDestination(e.target.value);setEdition('')}}>{selectedChoices.map(value=><option key={value} value={value}>{destinationNames[value]}</option>)}</select></label>
          {scoped(destination) && <label>Camp edition<select value={edition} onChange={e=>setEdition(e.target.value)} required><option value="">Choose edition</option>{editions.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>}
          <div className="studio-placement-buttons"><button type="submit" value="draft" disabled={busy}>Save draft placement</button>{user.can_publish_destinations && <button type="submit" value="publish" disabled={busy || current.archived}>Publish destination</button>}{user.can_publish_destinations && <button type="submit" value="withdraw" disabled={busy}>Withdraw destination</button>}</div>
          </form><small>Publishing requires the original media item to be approved. Private camper resources remain subject to camper entitlement; a placement cannot bypass it.</small>
          </div>
          <div className="studio-archive-actions"><button type="button" disabled={busy} onClick={()=>run(()=>studioArchiveAsset(current.id,current.archived?'restore':'archive'))}>{current.archived?'Restore to drafts':'Archive and withdraw all destinations'}</button></div>
        </>}
      </div>
    </div>
  </section>
}
