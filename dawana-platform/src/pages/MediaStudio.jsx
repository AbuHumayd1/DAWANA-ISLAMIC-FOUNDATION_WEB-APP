import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import { backendUrl } from '../services/productionContract'
import { studioSession, studioLogin, studioLogout, changeStudioPassword, studioLibrary, studioPublish, studioUpload, studioUploadStatus, studioEdit, studioLinkAsset, studioAssetMetadata, studioHostedLinks, studioPlacement, studioEditorialCollections, studioDeleteDraft } from '../services/mediaStudioApi'
import './MediaStudio.css'
import StaffPasswordChange from '../components/StaffPasswordChange'
import StudioDestinations from './StudioDestinations'
import StudioCarouselEditor from './StudioCarouselEditor'
import StudioLecturerAppearances from './StudioLecturerAppearances'
import StudioEditorial from './StudioEditorial'
import { hostedVideoThumbnail } from '../services/hostedVideoThumbnail'

const COMPOSER_FIELDS = {
  photos: [{ name: 'caption', label: 'Caption', required: true }, { name: 'alt_text', label: 'Accessible description', required: true }, { name: 'photograph', label: 'Photograph', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }],
  videos: [{ name: 'caption', label: 'Title / caption', required: true }, { name: 'alt_text', label: 'Thumbnail description', required: true }, { name: 'lecturer', label: 'Lecturer (optional)' }, { name: 'thumbnail', label: 'Thumbnail', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }, { name: 'recording_file', label: 'Video recording', file: true, accept: 'video/mp4,video/webm', required: true }],
  recordings: [{ name: 'title', label: 'Recording title', required: true }, { name: 'lecturer', label: 'Lecturer' }, { name: 'description', label: 'Description' }, { name: 'audio', label: 'Audio recording', file: true, accept: 'audio/mpeg,audio/mp4,audio/wav,audio/ogg', required: true }],
  flyers: [{ name: 'title', label: 'Official flyer title', required: true }, { name: 'alt_text', label: 'Accessible description', required: true }, { name: 'image', label: 'Official camp flyer image', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }],
  promotions: [{ name: 'title', label: 'Promotion title', required: true }, { name: 'description', label: 'Description' }, { name: 'alt_text', label: 'Poster description', required: true }, { name: 'poster', label: 'Poster', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }, { name: 'video', label: 'H.264/AAC MP4', file: true, accept: 'video/mp4', required: true }],
  lecturers: [{ name: 'name', label: 'Lecturer name', required: true }, { name: 'designation', label: 'Designation' }, { name: 'biography', label: 'Biography', required: true }, { name: 'alt_text', label: 'Portrait description', required: true }, { name: 'photograph', label: 'Lecturer portrait', file: true, accept: 'image/jpeg,image/png,image/webp', required: true }],
  activities: [{ name: 'title', label: 'Activity title', required: true }, { name: 'category', label: 'Category', required: true }, { name: 'description', label: 'Description', required: true }, { name: 'alt_text', label: 'Photo description (if supplied)' }, { name: 'photograph', label: 'Optional activity photograph', file: true, accept: 'image/jpeg,image/png,image/webp' }],
}

const LIBRARIES = [
  { key: 'photos', name: 'Photographs & Galleries', count: 'Camp photos and memories', icon: '📷' },
  { key: 'videos', name: 'Videos & Livestreams', count: 'Upload videos or paste links', icon: '▶' },
  { key: 'hosted', name: 'YouTube & Live', count: 'Hosted links', icon: '▶' },
  { key: 'recordings', name: 'Lecture Audio', count: 'Recorded lectures', icon: '🎙' },
  { key: 'flyers', name: 'Official Camp Flyers', count: 'Approved DIC flyers', icon: '▧' },
  { key: 'promotions', name: 'Promotional Videos', count: 'DIC introductions and experiences', icon: '✦' },
  { key: 'lecturers', name: 'Lecturer Profiles', count: 'Portraits and biographies', icon: '♙' },
  { key: 'appearances', name: 'Lecturer Appearances', count: 'Existing lecturer programmes', icon: '◫' },
  { key: 'activities', name: 'Camp Activities', count: 'Activities with optional photos', icon: '▤' },
]

// Destinations are restricted by the existing StudioPlacement backend allow-list.
const PUBLISH_DESTINATIONS = {
  photos: [['foundation_archive', 'Media page — All Videos / All Audio + chosen collection'], ['foundation_home', 'Homepage — Latest 3 featured media'], ['dic_memories', 'DIC memories gallery'], ['dic_landing', 'DIC landing page']],
  videos: [['foundation_archive', 'Media page — All Videos / All Audio + chosen collection'], ['foundation_home', 'Homepage — Latest 3 featured media'], ['dic_landing', 'DIC landing page']],
  hosted: [['foundation_archive', 'Media page — All Videos / All Audio + chosen collection'], ['foundation_home', 'Homepage — Latest 3 featured media'], ['dic_landing', 'DIC landing page'], ['dic_resources', 'DIC lecture resources']],
  recordings: [['foundation_archive', 'Media page — All Audio + chosen collection'], ['camper_resources', 'Camper Portal — private lecture audio']],
  flyers: [['foundation_archive', 'Media page — All Videos / All Audio + chosen collection'], ['dic_landing', 'DIC landing page']],
  promotions: [['foundation_archive', 'Media page — All Videos / All Audio + chosen collection'], ['foundation_home', 'Homepage — Latest 3 featured media'], ['dic_landing', 'DIC landing page']],
  lecturers: [], appearances: [],
  activities: [['foundation_archive', 'Media page — All Videos / All Audio + chosen collection'], ['dic_landing', 'DIC landing page']],
}
const needsEdition = destination => destination.startsWith('dic_') || destination === 'camper_resources'
const MEDIA_CATEGORIES = [['general','General Foundation media'],['dic','Darul Islam Camp'],['ramadan','Ramadan Tafseer'],['shorts','Short videos'],['other','Other programmes (youth outreach, podcasts, events)']]
function categoryMetadata(category, series) {
  return {programme: category, ...(['other','ramadan'].includes(category) ? {event: series.trim()} : {})}
}
function MediaCategoryInput({value, onChange, audio = false, customCollections = []}) {
  return <label>Media collection
    <select value={value} onChange={event => onChange(event.target.value)}>
      {[...MEDIA_CATEGORIES, ...customCollections.map(c => [c.slug, c.title])].filter(([key]) => !audio || key !== 'shorts').map(([key,label]) => <option key={key} value={key}>{label}</option>)}
    </select>
    <small>Also appears in All Videos or All Audio when published to the public archive.</small>
  </label>
}

function StudioPublishChoices({choices, selected, setSelected, authorized}) {
  if (!authorized) return null
  return <fieldset className="studio-publish-choices">
    <legend>Where should this appear?</legend>
    <p>Select <strong>Media page — All Videos / All Audio</strong> to show this in the appropriate format archive and the programme collection selected above. Select other destinations only when needed. Camper Portal audio stays private.</p>
    <div className="studio-publish-options">{choices.map(([key, name]) =>
      <label key={key}><input type="checkbox" checked={selected.includes(key)} onChange={event =>
        setSelected(previous => event.target.checked
          ? [...previous.filter(value => value !== key), key]
          : previous.filter(value => value !== key))} />{name}</label>
    )}</div>
  </fieldset>
}

function StudioAppearanceButton() {
  const appearance = window.DawanaAppearance
  const preference = useSyncExternalStore(appearance.subscribe, appearance.getSnapshot)
  const dark = preference.theme === 'dark'
  return <button className="studio-appearance-button" type="button"
    onClick={appearance.toggle} aria-label={dark ? 'Switch Media Studio to light mode' : 'Switch Media Studio to dark mode'}
    title={dark ? 'Switch to light mode' : 'Switch to dark mode'}>
    <span aria-hidden="true">{dark ? '☀' : '☾'}</span>
    <span>{dark ? 'Light mode' : 'Dark mode'}</span>
  </button>
}

export default function MediaStudio() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [message, setMessage] = useState('')
  const [loginBusy, setLoginBusy] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [library, setLibrary] = useState('photos')
  const [q, setQ] = useState('')
  const [state, setState] = useState('')
  const [edition, setEdition] = useState('')
  const [rows, setRows] = useState([])
  const [page, setPage] = useState(1)
  const [canPublish, setCanPublish] = useState(false)
  const [canEdit, setCanEdit] = useState(false)
  const [canCreate, setCanCreate] = useState(false)
  const [canDelete, setCanDelete] = useState(false)
  const [hostedLinks, setHostedLinks] = useState('')
  const [hostedMode, setHostedMode] = useState('single')
  const [hostedTitle, setHostedTitle] = useState('')
  const [hostedUrl, setHostedUrl] = useState('')
  const [hostedLecturer, setHostedLecturer] = useState('')
  const [hostedDescription, setHostedDescription] = useState('')
  const [mediaCategory, setMediaCategory] = useState('general')
  const [customCollections, setCustomCollections] = useState([])
  const [mediaProgrammeName, setMediaProgrammeName] = useState('')
  const [itemMediaCategory, setItemMediaCategory] = useState('general')
  const [itemProgrammeName, setItemProgrammeName] = useState('')
  const [hostedEdition, setHostedEdition] = useState('')
  const [editing, setEditing] = useState(null)
  const [preview, setPreview] = useState(null)
  const [focusAsset, setFocusAsset] = useState('')
  const [loading, setLoading] = useState(false)
  const [more, setMore] = useState(false)
  const [pending, setPending] = useState(null)
  const [itemToPublish, setItemToPublish] = useState(null)
  const [itemDestinations, setItemDestinations] = useState([])
  const [itemEdition, setItemEdition] = useState('')
  const [uploadInfo, setUploadInfo] = useState({ enabled: false, editions: [], libraries: [], approved_providers: null })
  const [composerOpen, setComposerOpen] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const [publishDestinations, setPublishDestinations] = useState([])

  const menuRef = useRef(null)
  const seq = useRef(0)
  function chooseLibrary(kind) {
    setPage(1)
    setLibrary(kind)
    setMessage('')
    setQ('')
    setState('')
    setEdition('')
    setMenuOpen(false)
    setComposerOpen(false)
    // A collection card should take the editor to its workspace, not just
    // silently change a section far below the fold.
    window.requestAnimationFrame(() => {
      document.getElementById('studio-library')?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
        block: 'start',
      })
    })
  }
  useEffect(() => {
    let mounted = true
    studioSession().then(v => { if (mounted) setUser(v) })
      .catch(() => {}).finally(() => { if (mounted) setChecking(false) })
    return () => { mounted = false }
  }, [])
  useEffect(() => {
    if (!user?.can_manage_catalogue) return
    studioEditorialCollections().then(data => setCustomCollections(data.collections || [])).catch(() => setCustomCollections([]))
  }, [user])
  useEffect(() => {
    if (!user) return
    studioUploadStatus().then(setUploadInfo).catch(() => setUploadInfo({ enabled: false, editions: [], libraries: [], approved_providers: null }))
  }, [user])
  useEffect(() => {
    setComposerOpen(false); setPreview(null); setEditing(null)
    setPublishDestinations(['hosted','videos'].includes(library) ? ['foundation_archive'] : [])
    setItemToPublish(null); setItemDestinations([]); setItemEdition('')
  }, [library])
  useEffect(() => {
    if (!preview) return undefined
    function closeOnEscape(event) { if (event.key === 'Escape') setPreview(null) }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [preview])
  const [failedThumbnails, setFailedThumbnails] = useState({})
  function safePlayer(value) {
    try {
      const url = new URL(value)
      return url.protocol === 'https:' && ['www.youtube-nocookie.com', 'player.vimeo.com'].includes(url.hostname)
        && !url.username && !url.password && !url.hash && !url.port ? url.href : ''
    } catch { return '' }
  }
  function selectedPublication(editionId) {
    const destinations = publishDestinations.filter(key =>
      (PUBLISH_DESTINATIONS[library] || []).some(([id]) => id === key))
    if (!destinations.length) throw new Error('Choose at least one place for the media to appear.')
    if (destinations.some(needsEdition) && !editionId) {
      throw new Error('Choose the camp edition before publishing to a DIC or Camper Portal section.')
    }
    return destinations.map(destination => ({destination, edition: needsEdition(destination) ? editionId : null}))
  }
  async function publishCreated(kind, sourceId, existingAssetId, placements, category = 'general', eventName = '', fullCaption = '') {
    // The existing backend rechecks all permissions and validation at each step.
    // Do not retry successful operations or claim atomicity across HTTP requests.
    const stage = {sourceId, stage: 'draft saved', destinations: []}
    try {
      await studioPublish(kind, sourceId, 'publish')
      stage.stage = 'original published'
      const assetId = existingAssetId || (await studioLinkAsset(kind, sourceId)).asset?.id
      if (!assetId) throw new Error('Could not link the published item to the Foundation catalogue.')
      stage.stage = 'linked to catalogue'
      const metadata = {
        ...(['hosted','videos','recordings'].includes(kind) ? categoryMetadata(category, eventName) : {}),
        ...(fullCaption ? {description: fullCaption} : {}),
      }
      if (Object.keys(metadata).length) {
        await studioAssetMetadata(assetId, metadata)
        stage.stage = 'saved public caption and collection metadata'
      }
      for (const placement of placements) {
        await studioPlacement(assetId, placement.destination, 'publish', placement.edition)
        stage.destinations.push(placement.destination)
      }
      stage.stage = 'published to all selected destinations'
      return stage
    } catch (error) {
      error.studioProgress = stage
      throw error
    }
  }
  function failWithProgress(error, createdCount) {
    const progress = error.studioProgress
    if (!progress) return createdCount
      ? `${createdCount} draft(s) saved, but remaining work stopped: ${error.message}. Check saved items before trying again.`
      : error.message
    return `Media record #${progress.sourceId}: ${progress.stage}; ${progress.destinations.length} destination(s) published. ${error.message}. Check existing media before retrying to avoid duplicates.`
  }
  async function addHostedLinks(event) {
    event.preventDefault()
    const action = event.nativeEvent.submitter?.value === 'publish' ? 'publish' : 'draft'
    if (Array.isArray(uploadInfo.approved_providers) && uploadInfo.approved_providers.length === 0) {
      setMessage('YouTube and Vimeo links are not enabled on the production server. An administrator needs to configure the approved video providers before you can save a link.')
      return
    }
    const lines = hostedMode === 'single'
      ? [`${hostedTitle.trim()} | ${hostedUrl.trim()}`]
      : hostedLinks.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
    if (!lines.length || lines.length > 25) {
      setMessage('Provide between 1 and 25 YouTube/Vimeo links per batch.'); return
    }
    const entries = lines.map(line => {
      const separator = line.indexOf('|')
      return separator < 0 ? null : {
        title: line.slice(0, separator).trim(),
        video_url: line.slice(separator + 1).trim(),
        lecturer: hostedLecturer.trim(),
        description: hostedDescription.trim(),
        ...(hostedEdition ? { edition: hostedEdition } : {}),
      }
    })
    if (entries.some(entry => !entry?.title || !entry?.video_url)) {
      setMessage(hostedMode === 'single'
        ? 'Enter a video title and a valid YouTube/Vimeo link.'
        : 'Each line needs its title, a vertical bar (|), then the video URL.'); return
    }
    let placements = []
    try {
      if (action === 'publish') {
        if (!canPublishImmediately) throw new Error('You do not have permission to publish this collection.')
        placements = selectedPublication(hostedEdition)
      }
    } catch (error) { setMessage(error.message); return }
    setUploadBusy(true); setMessage('')
    try {
      const response = await studioHostedLinks(entries)
      const created = response.items || []
      setRevision(n => n + 1)
      if (action === 'publish') {
        const results = []
        for (const item of created) {
          try { results.push(await publishCreated('hosted', item.id, item.asset_id, placements, mediaCategory, mediaProgrammeName)) }
          catch (error) {
            setMessage(`${results.length} of ${created.length} videos published. ${failWithProgress(error, created.length)}`)
            return
          }
        }
        setMessage(`${results.length} video(s) published to ${placements.length} selected destination(s).`)
      } else {
        if (user.can_manage_catalogue) {
          let tagged = 0
          for (const item of created) {
            try {
              await studioAssetMetadata(item.asset_id, categoryMetadata(mediaCategory, mediaProgrammeName))
              tagged++
            } catch (error) {
              setMessage(`${created.length} video drafts saved; only ${tagged} classified. ${error.message}. Review saved items instead of submitting duplicates.`)
              return
            }
          }
        }
        setMessage(`${created.length} video link(s) saved privately as drafts with their chosen collection.`)
      }
      setHostedLinks(''); setHostedTitle(''); setHostedUrl('')
      setComposerOpen(false)
      setRevision(n => n + 1)
    } catch (error) { setMessage(error.message) }
    finally { setUploadBusy(false) }
  }
  async function upload(event) {
    event.preventDefault()
    const action = event.nativeEvent.submitter?.value === 'publish' ? 'publish' : 'draft'
    const form = event.currentTarget
    const formData = new FormData(form)
    const values = Object.fromEntries(formData)
    const publicationDescription = String(values.publication_description || '').trim()
    delete values.publication_description
    const photos = library === 'photos'
      ? formData.getAll('photograph').filter(file => file instanceof File && file.name && file.size) : []
    if (library === 'photos' && photos.length > 20) {
      setMessage('Select up to 20 photographs per batch.'); return
    }
    let placements = []
    if (publicationDescription && !user.can_manage_catalogue) {
      setMessage('Long publication captions require Media Studio catalogue permission. Ask an administrator to enable that permission.'); return
    }
    try {
      if (action === 'publish') {
        if (!canPublishImmediately) throw new Error('You do not have permission to publish this collection.')
        placements = selectedPublication(values.edition)
      }
    } catch (error) { setMessage(error.message); return }
    setUploadBusy(true); setMessage('')
    let saved = 0, published = 0
    try {
      const batch = photos.length > 1 ? photos.map(photograph => ({...values, photograph})) : [values]
      for (const fields of batch) {
        const created = await studioUpload(library, fields)
        saved++
        setRevision(current => current + 1)
        if (action === 'publish') {
          try {
            await publishCreated(library, created.id, null, placements, mediaCategory, mediaProgrammeName, publicationDescription)
            published++
          } catch (error) {
            setMessage(`${saved} draft(s) saved, ${published} published. ${failWithProgress(error, saved)}`)
            return
          }
        } else if (user.can_manage_catalogue && (['videos','recordings'].includes(library) || publicationDescription)) {
          try {
            const {asset} = await studioLinkAsset(library, created.id)
            if (!asset?.id) throw new Error('Could not index the saved media.')
            const metadata = {
              ...(['videos','recordings'].includes(library) ? categoryMetadata(mediaCategory, mediaProgrammeName) : {}),
              ...(publicationDescription ? {description: publicationDescription} : {}),
            }
            await studioAssetMetadata(asset.id, metadata)
          } catch (error) {
            setMessage(`${saved} draft(s) saved but classification failed: ${error.message}. Review saved items before retrying.`)
            return
          }
        }
      }
      setMessage(action === 'publish'
        ? `${published} media item(s) published to ${placements.length} chosen destination(s).`
        : `${saved} media item(s) saved privately as drafts. You can publish them later.`)
      setComposerOpen(false)
    } catch (error) {
      setMessage(failWithProgress(error, saved))
    } finally {
      if (saved) setRevision(current => current + 1)
      setUploadBusy(false)
    }
  }
  useEffect(() => {
    if (!menuOpen) return
    function escape(event) { if (event.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [menuOpen])
  useEffect(() => {
    if (!user) return
    if (!user.libraries?.includes(library)) {
      setLibrary(user.libraries?.[0] || 'photos')
      return
    }
    let active = true
    const current = ++seq.current
    setLoading(true)
    studioLibrary({ library, q, state, edition, page })
      .then(data => { if (active && current === seq.current) { setRows(previous => page === 1 ? data.items : [...previous.filter(item => !data.items.some(next => next.id === item.id)), ...data.items]); setMore(data.has_more); setCanPublish(data.can_publish); setCanEdit(data.can_edit); setCanCreate(data.can_create); setCanDelete(data.can_delete) } })
      .catch(e => { if (active && current === seq.current) { setRows([]); setMessage(e.message) } })
      .finally(() => { if (active && current === seq.current) setLoading(false) })
    return () => { active = false }
  }, [user, library, q, state, edition, revision, page])
  async function signIn(event) {
    event.preventDefault(); setLoginBusy(true); setMessage('')
    const form = new FormData(event.currentTarget)
    try { setUser(await studioLogin(form.get('username'), form.get('password'))) }
    catch (error) { setMessage(error.message) }
    finally { setLoginBusy(false) }
  }
  async function signOut() {
    try { await studioLogout(); setUser(null); setRows([]); setMenuOpen(false) }
    catch (error) { setMessage(error.message) }
  }
  async function addToFoundation(item) {
    setPending(item.id); setMessage('')
    try {
      const result = await studioLinkAsset(library, item.id)
      setFocusAsset(result.asset?.id || '')
      setRevision(current => current + 1)
      setMessage(result.created ? 'Media linked to the Foundation catalogue. Choose publication destinations below.' : 'Already linked to the Foundation catalogue. Manage destinations below.')
    } catch (error) { setMessage(error.message) }
    finally { setPending(null) }
  }
  async function saveMetadata(event, item) {
    event.preventDefault()
    setPending(item.id); setMessage('')
    const values = Object.fromEntries(new FormData(event.currentTarget))
    const metadata = {}
    for (const [key, original] of Object.entries(item.metadata || {})) {
      if (typeof original === 'boolean') metadata[key] = values[key] === 'on'
      else if (typeof original === 'number') metadata[key] = Number(values[key])
      else metadata[key] = values[key] || ''
    }
    try {
      const response = await studioEdit(library, item.id, metadata)
      setRows(previous => previous.map(row => row.id === item.id ? { ...row, metadata: response.metadata, state: response.state, title: response.metadata.title || response.metadata.name || response.metadata.caption || row.title } : row))
      setEditing(null)
      setMessage('Changes saved. Previously published material has been returned to draft for review.')
    } catch (error) { setMessage(error.message) }
    finally { setPending(null) }
  }
  async function deleteDraft(item) {
    if (item.state !== 'draft' || !canDelete) return
    if (!window.confirm(`Delete draft “${item.title}” from Media Studio? This cannot be undone. If this item was published and later withdrawn, only a system administrator can remove it, and its publication history will be retained. Media linked to a publishing destination cannot be deleted.`)) return
    setPending(item.id); setMessage('')
    try {
      await studioDeleteDraft(library, item.id, Boolean(user?.owner))
      setRows(previous => previous.filter(row => row.id !== item.id))
      if (editing === item.id) setEditing(null)
      if (itemToPublish === item.id) setItemToPublish(null)
      setMessage('Draft deleted from the workspace. Existing public publications and shared storage files are unaffected.')
      setRevision(current => current + 1)
    } catch (error) {
      setMessage(error.message || 'Draft could not be deleted.')
    } finally { setPending(null) }
  }
  async function publishExisting(item, action, chosen = []) {
    setPending(item.id); setMessage('')
    try {
      if (action === 'withdraw') {
        await studioPublish(library, item.id, 'withdraw')
        setMessage(`${item.title} withdrawn. Previously published destinations have also been withdrawn.`)
      } else {
        if (!canPublishImmediately) throw new Error('Publication permission is required for this workflow.')
        if (!chosen.length) throw new Error('Choose at least one destination.')
        if (chosen.some(needsEdition) && !itemEdition) throw new Error('Choose the camp edition.')
        // Publish original only if still a draft. No automatic retry on failure.
        if (item.state !== 'published') await studioPublish(library, item.id, 'publish')
        const {asset} = await studioLinkAsset(library, item.id)
        if (!asset?.id) throw new Error('Could not link media to the Foundation catalogue.')
        if (['hosted','videos','recordings'].includes(library))
          await studioAssetMetadata(asset.id, categoryMetadata(itemMediaCategory, itemProgrammeName))
        let completed = 0
        for (const dest of chosen) {
          try {
            await studioPlacement(asset.id, dest, 'publish',
              needsEdition(dest) ? itemEdition : null)
            completed++
          } catch (error) {
            setMessage(`${item.title}: original published and ${completed} of ${chosen.length} destinations updated. ${error.message}. Review before retrying.`)
            setRevision(v => v + 1)
            return
          }
        }
        setFocusAsset(asset.id)
        setItemToPublish(null)
        setItemDestinations([])
        setMessage(`${item.title} published to ${completed} chosen destination(s).`)
      }
      setRevision(v => v + 1)
    } catch (error) {
      setMessage(`${item.title}: ${error.message}. The original may already be published; check it before retrying.`)
      setRevision(v => v + 1)
    } finally { setPending(null) }
  }
  if (checking) return <main className="studio-checking" aria-busy="true">Opening the secure DAWANA Media Studio…</main>
  if (!user) return <main className="studio-login"><div className="studio-login-appearance"><StudioAppearanceButton /></div><Link to="/" className="studio-back">← DAWANA Islamic Foundation</Link><section className="studio-login-card">
    <span className="studio-kicker">THE CREATIVE WORKSPACE</span>
    <h1>Every story deserves a beautiful home.</h1>
    <p>DAWANA Media Studio — a private workspace for our Foundation media team.</p>
    <form onSubmit={signIn}><label>Staff username or email<input name="username" autoComplete="username" required maxLength="150" /></label>
    <label>Password<input type="password" name="password" autoComplete="current-password" required /></label>
    {message && <p role="alert" className="studio-error">{message}</p>}
    <button type="submit" disabled={loginBusy}>{loginBusy ? 'Signing in…' : 'Enter Media Studio'} <span aria-hidden="true">→</span></button></form>
    <small>Authorized personnel only. Your existing DAWANA staff credentials are used.</small>
  </section></main>

  const selected = LIBRARIES.find(x => x.key === library)
  const displayName = ['hosted', 'videos'].includes(library) ? 'Videos & Livestreams'
    : ['lecturers', 'appearances'].includes(library) ? 'Lecturer Profiles' : selected?.name
  const showCollections = LIBRARIES.filter(x => !['hosted', 'appearances'].includes(x.key)
    && (user.libraries?.includes(x.key)
      || x.key === 'videos' && user.libraries?.includes('hosted')
      || x.key === 'lecturers' && user.libraries?.includes('appearances')))
  const selectCollection = key => {
    const target = key === 'videos' && user.libraries?.includes('hosted') ? 'hosted'
      : key === 'lecturers' && !user.libraries?.includes('lecturers') && user.libraries?.includes('appearances')
        ? 'appearances' : key
    chooseLibrary(target)
  }
  const publishedInView = rows.filter(item => item.state === 'published').length
  const draftsInView = rows.filter(item => item.state === 'draft').length
  const isHosted = library === 'hosted'
  const hostedProviderDisabled = isHosted && Array.isArray(uploadInfo.approved_providers) && uploadInfo.approved_providers.length === 0
  const hasUploadForm = Boolean(COMPOSER_FIELDS[library])
  const canUploadFiles = hasUploadForm && uploadInfo.enabled && uploadInfo.libraries.includes(library) && canCreate
  const canPublishImmediately = canPublish && user.can_manage_catalogue && user.can_publish_destinations
    && (PUBLISH_DESTINATIONS[library] || []).length > 0
    && library !== 'lecturers' && library !== 'appearances'
  const selectedDestinations = publishDestinations.filter(key => (PUBLISH_DESTINATIONS[library] || []).some(([id]) => id === key))
  const selectionNeedsEdition = selectedDestinations.some(needsEdition)
  const uploadType = ({
    photos: 'photos', videos: 'videos', recordings: 'audio recordings',
    flyers: 'flyers', promotions: 'promotional videos',
    lecturers: 'lecturer profiles', activities: 'activities',
  })[library]
  return <div className="studio-app">
    <header className="studio-top">
      {menuOpen && <button className="studio-menu-backdrop" type="button" aria-label="Close Media Studio navigation" onClick={() => setMenuOpen(false)} />}
      <div className="studio-nav-wrapper" ref={menuRef}><button className="studio-hamburger" aria-label={menuOpen ? 'Close Studio navigation' : 'Open Studio navigation'} aria-expanded={menuOpen} aria-controls="studio-menu" onClick={() => setMenuOpen(value => !value)}>{menuOpen ? '✕' : '☰'}</button>
      {menuOpen && <nav id="studio-menu" className="studio-popnav" aria-label="Media Studio sections">
        <strong>Media collections</strong>
        {showCollections.map(x => <button type="button" key={x.key} onClick={() => selectCollection(x.key)} aria-current={library === x.key ? 'page' : undefined}><span>{x.icon}</span>{x.name}</button>)}
        <div className="studio-menu-account">
          <strong>Account</strong>
          <button type="button" onClick={() => { setMenuOpen(false); setPasswordOpen(true) }}><span aria-hidden="true">⚙</span>Change password</button>
          <button type="button" onClick={() => { setMenuOpen(false); signOut() }}><span aria-hidden="true">↪</span>Sign out</button>
        </div>
      </nav>}</div>
      <Link to="/" className="studio-logo"><img src="/dawana-official-logo.png" alt="" /><span><strong>DAWANA</strong><small>MEDIA STUDIO</small></span></Link>
      <div className="studio-account"><span className="studio-identity">{user.display_name}{user.owner ? <small>System administrator</small> : <small>Media team</small>}</span><StudioAppearanceButton /></div>
    </header>
    {passwordOpen && <StaffPasswordChange onChangePassword={changeStudioPassword} onClose={() => setPasswordOpen(false)} />}
    <main className="studio-main">
      <div className="studio-overview"><div><span className="studio-kicker">CREATIVE COMMAND CENTRE</span><h1>Capture. Curate. Share.</h1><p>One place for DAWANA's stories, lectures and memorable moments.</p></div><div className="studio-hero-art" aria-hidden="true">
          <div className="studio-hero-halo" />
          <svg className="studio-hero-trails" viewBox="0 0 420 260" fill="none" preserveAspectRatio="xMidYMid meet">
            <path className="studio-hero-trail studio-hero-trail-one" d="M18 172C100 164 86 46 208 58S332 172 405 92" />
            <path className="studio-hero-trail studio-hero-trail-two" d="M24 208C108 234 155 140 224 144S322 222 397 158" />
          </svg>
          <div className="studio-hero-frame studio-hero-frame-back"><span className="studio-hero-frame-top"><i /><i /><i /></span><span className="studio-hero-frame-landscape"><b /><em /></span></div>
          <div className="studio-hero-frame studio-hero-frame-front"><span className="studio-hero-frame-top"><i /><i /><i /></span><span className="studio-hero-play"><svg viewBox="0 0 32 32" fill="none"><path d="M11 7.5L25 16 11 24.5V7.5Z" fill="currentColor" /></svg></span><span className="studio-hero-frame-caption"><i /><i /></span></div>
          <div className="studio-hero-audio"><span className="studio-hero-audio-disc"><svg viewBox="0 0 24 24" fill="none"><path d="M9 4v11.5a3.5 3.5 0 1 1-2-3.16V7l10-2v8.5a3.5 3.5 0 1 1-2-3.16V3L9 4Z" fill="currentColor" /></svg></span><span className="studio-hero-wave">{Array.from({ length: 16 }, (_, i) => <i key={i} style={{ '--bar': i % 5, '--phase': i % 7 }} />)}</span></div>
          <span className="studio-hero-signal studio-hero-signal-one" /><span className="studio-hero-signal studio-hero-signal-two" />
        </div></div>
      <section className="studio-collections" aria-label="Media collections"><h2>Explore collections</h2><div className="studio-collection-grid">{showCollections.map(x => <button key={x.key} type="button" className={'studio-collection' + (library === x.key || x.key === 'videos' && library === 'hosted' || x.key === 'lecturers' && library === 'appearances' ? ' active' : '')} onClick={() => selectCollection(x.key)}><span className="studio-collection-icon">{x.icon}</span><strong>{x.name}</strong><small>{x.count}</small></button>)}</div></section>
      <section id="studio-library" className="studio-workspace" aria-labelledby="studio-library-title">
        <div className="studio-heading"><div><span className="studio-kicker">YOUR COLLECTION</span><h2 id="studio-library-title">{displayName}</h2><p>Start by adding something new, or browse items already saved here.</p></div><span className="studio-library-meta">{rows.length} loaded · {publishedInView} published · {draftsInView} drafts</span></div>
        {['hosted', 'videos'].includes(library) && <div className="studio-media-mode" role="group" aria-label="Choose video format">
          {user.libraries?.includes('hosted') && <button type="button" aria-pressed={library === 'hosted'} onClick={() => chooseLibrary('hosted')}>YouTube / Vimeo link</button>}
          {user.libraries?.includes('videos') && <button type="button" aria-pressed={library === 'videos'} onClick={() => chooseLibrary('videos')}>Upload video file</button>}
        </div>}
        {['lecturers', 'appearances'].includes(library) && <div className="studio-media-mode" role="group" aria-label="Lecturer management">
          {user.libraries?.includes('lecturers') && <button type="button" aria-pressed={library === 'lecturers'} onClick={() => chooseLibrary('lecturers')}>Lecturer profiles</button>}
          {user.libraries?.includes('appearances') && <button type="button" aria-pressed={library === 'appearances'} onClick={() => chooseLibrary('appearances')}>Camp appearances</button>}
        </div>}
        {library === 'appearances' && <StudioLecturerAppearances />}
        <div className="studio-start-panel">
          <div className="studio-start-copy">
            <span className="studio-kicker">START HERE</span>
            <h3>{isHosted ? 'Add a YouTube video or livestream' : hasUploadForm ? `Add ${uploadType}` : 'Manage lecturer appearances'}</h3>
            <p>{isHosted
              ? 'Paste a video link, choose where it should appear, then save a draft or publish immediately.'
              : hasUploadForm
                ? 'Choose a file, enter its details, then save a draft or publish to the selected website sections.'
                : 'Appearance records come from existing lecturer and programme information. Browse existing records below.'}</p>
            {hostedProviderDisabled && <p className="studio-upload-pending" role="alert">YouTube and Vimeo links are currently disabled in production. Please ask the administrator to enable approved video providers on Render. Your form details will stay here.</p>}
            {hasUploadForm && !canUploadFiles && <p className="studio-upload-pending" role="note">
              {canCreate ? 'File uploads are not active yet. The Foundation must first approve and connect private R2 storage. Existing records can still be viewed and managed.' : 'Your staff role cannot upload files to this collection.'}
            </p>}
          </div>
          <div className="studio-start-actions">
            {isHosted && canCreate ? <button className="studio-create" type="button" aria-expanded={composerOpen} onClick={() => setComposerOpen(open => !open)}>{composerOpen ? 'Close link form' : '+ Add video links'}</button>
              : hasUploadForm ? <button className="studio-create" type="button" disabled={!canUploadFiles} aria-expanded={canUploadFiles && composerOpen} onClick={() => setComposerOpen(open => !open)}>{canUploadFiles ? composerOpen ? 'Close upload form' : `+ Upload ${uploadType}` : `Upload ${uploadType} — unavailable`}</button>
                : null}
            {(isHosted || hasUploadForm) && <small>{isHosted ? 'No file upload or R2 storage needed.' : canUploadFiles ? 'Saving drafts and publishing remain permission-controlled.' : 'Uploads will become available after approved storage activation.'}</small>}
          </div>
        </div>
        <div className="studio-next-steps" aria-label="How Media Studio works"><span><b>1.</b> Add your media and choose destinations</span><span><b>2.</b> Save Draft or Publish Now</span></div>
        {library === 'hosted' && composerOpen && canCreate && <form className="studio-composer studio-hosted-composer" onSubmit={addHostedLinks}>
          <div><span className="studio-kicker">YOUTUBE · LIVESTREAMS · VIMEO</span><h3>Add video links</h3><p>Give the video a title, paste its YouTube or Vimeo URL, then save it as a private draft. This works for livestreams too; no file upload or R2 storage required.</p></div>
          <div className="studio-hosted-mode" role="group" aria-label="Number of videos to add">
            <button type="button" aria-pressed={hostedMode === 'single'} onClick={() => setHostedMode('single')}>One video</button>
            <button type="button" aria-pressed={hostedMode === 'bulk'} onClick={() => setHostedMode('bulk')}>Several videos</button>
          </div>
          {hostedMode === 'single' ? <>
            <label>Video title<input required value={hostedTitle} onChange={e => setHostedTitle(e.target.value)} placeholder="e.g. Friday lecture" maxLength={200} /></label>
            <label>YouTube or Vimeo link<input required type="url" value={hostedUrl} onChange={e => setHostedUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." /></label>
          </> : <label className="studio-hosted-lines">Video titles and links (up to 25)<textarea required rows={6} value={hostedLinks} onChange={e => setHostedLinks(e.target.value)} placeholder={'Friday Lecture | https://www.youtube.com/watch?v=VIDEO_ID\nSpecial Programme | https://www.youtube.com/live/VIDEO_ID'} /><small>Enter one video per line in this format: Title | URL. Up to 25 links per batch.</small></label>}
          <label>Lecturer / presenter (optional)<input value={hostedLecturer} onChange={e => setHostedLecturer(e.target.value)} maxLength={200}/></label>
          <label>Camp edition {selectionNeedsEdition ? '(required for selected destinations)' : '(optional)'}<select value={hostedEdition} onChange={e => setHostedEdition(e.target.value)}><option value="">Foundation-wide</option>{uploadInfo.editions.map(item => <option key={item.id} value={item.id}>{item.name} ({item.year})</option>)}</select></label>
          <label className="studio-hosted-lines">Description for these entries (optional)<textarea rows={2} value={hostedDescription} onChange={e => setHostedDescription(e.target.value)} maxLength={5000}/></label>
          <MediaCategoryInput value={mediaCategory} onChange={setMediaCategory} audio={library === 'recordings'} customCollections={customCollections}/>
            {['ramadan','other'].includes(mediaCategory) && <label>Programme / series (optional)<input value={mediaProgrammeName} onChange={e=>setMediaProgrammeName(e.target.value)} maxLength={150} placeholder="e.g. Ramadan Tafseer 2026, Youth Outreach, Podcast"/></label>}
            <StudioPublishChoices choices={PUBLISH_DESTINATIONS[library] || []} selected={publishDestinations} setSelected={setPublishDestinations} authorized={canPublishImmediately} />
          <div className="studio-submit-actions">
            <button type="submit" value="draft" disabled={uploadBusy || hostedProviderDisabled}>{uploadBusy ? 'Saving…' : 'Save Draft'}</button>
            {canPublishImmediately && <button type="submit" value="publish" disabled={uploadBusy || hostedProviderDisabled || !selectedDestinations.length || selectionNeedsEdition && !hostedEdition}>{uploadBusy ? 'Publishing…' : 'Publish Now'}</button>}
          </div>
        </form>}
        {composerOpen && canUploadFiles && <form className="studio-composer" onSubmit={upload} encType="multipart/form-data"><div><span className="studio-kicker">NEW MEDIA</span><h3>Add {displayName}</h3><p>Your files are kept private while saving. Publish Now is available only to authorized staff with a selected destination.</p></div>
          {library !== 'lecturers' && <label>Edition<select name="edition" required defaultValue=""><option value="">Select camp edition</option>{uploadInfo.editions.map(item => <option key={item.id} value={item.id}>{item.name} ({item.year})</option>)}</select></label>}
          {library === 'promotions' && <><label>Promotion type<select required name="kind"><option value="introduction">Upcoming introduction</option><option value="experience">Previous participant experience</option></select></label><label>Previous source edition (for experience videos)<select name="source_edition" defaultValue=""><option value="">Not applicable</option>{uploadInfo.editions.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></>}
          {COMPOSER_FIELDS[library]?.map(field => <label key={field.name}>{field.label}{['description','biography'].includes(field.name)
            ? <textarea name={field.name} rows={5} required={field.required} maxLength={5000} />
            : <input name={field.name} type={field.file ? 'file' : 'text'} multiple={library === 'photos' && field.name === 'photograph'} accept={field.accept} required={field.required} maxLength={field.file ? undefined : field.name === 'caption' ? 300 : field.name === 'alt_text' ? 250 : 2000} />}</label>)}
          {['photos','videos','promotions','activities','flyers'].includes(library) && <label className="studio-long-caption">Full publication caption / story (optional)
            <textarea name="publication_description" rows={7} maxLength={5000} placeholder="Write the complete message, announcement, context, or story. This will appear below the media, never over the image." />
            <small>Up to 5,000 characters. The short title stays separate from the full caption. All selected photos in a batch receive this caption.</small>
          </label>}
          {['videos','recordings'].includes(library) && <><MediaCategoryInput value={mediaCategory} onChange={setMediaCategory} audio={library === 'recordings'} customCollections={customCollections}/>
            {['ramadan','other'].includes(mediaCategory) && <label>Programme / series (optional)<input value={mediaProgrammeName} onChange={e=>setMediaProgrammeName(e.target.value)} maxLength={150} placeholder="e.g. Ramadan Tafseer 2026, Youth Outreach, Podcast"/></label>}
            </>}
            <StudioPublishChoices choices={PUBLISH_DESTINATIONS[library] || []} selected={publishDestinations} setSelected={setPublishDestinations} authorized={canPublishImmediately} />
          <div className="studio-submit-actions">
            <button type="submit" value="draft" disabled={uploadBusy}>{uploadBusy ? 'Saving…' : 'Save Draft'}</button>
            {canPublishImmediately && <button type="submit" value="publish" disabled={uploadBusy || !selectedDestinations.length}>{uploadBusy ? 'Publishing…' : 'Publish Now'}</button>}
          </div>
        </form>}
        <details className="studio-filters-toggle"><summary>Search and filter saved items</summary><div className="studio-filters"><label>Search<input aria-label="Search media" placeholder="Search titles and captions" value={q} onChange={e => { setPage(1); setQ(e.target.value) }} /></label>
          <label>Publication status<select aria-label="Filter publication status" value={state} onChange={e => { setPage(1); setState(e.target.value) }}><option value="">All statuses</option><option value="draft">Draft</option>{library !== 'hosted' && <option value="review">Review</option>}<option value="published">Published</option></select></label>
          {!['lecturers'].includes(library) && <label>Camp edition ID<input aria-label="Filter edition" inputMode="numeric" placeholder="All editions" value={edition} onChange={e => { setPage(1); setEdition(e.target.value.replace(/[^0-9]/g,'')) }}/></label>}
        </div></details>
        {message && <p className="studio-notice" role="status">{message}</p>}
        {loading ? <p className="studio-state">Loading media catalogue…</p> : rows.length ? <div className="studio-item-grid">{rows.map(item => <article className="studio-item" key={item.id}>
          <div className={'studio-art' + (item.preview_url || item.player_url ? ' studio-art-available' : '')}>
            {item.preview_url && item.preview_url.includes('/private-preview/') ? <button className="studio-preview-trigger studio-play-trigger" type="button" onClick={() => setPreview({kind: library === 'recordings' ? 'private-audio' : 'private-video', url: backendUrl(item.preview_url), title: item.title})} aria-label={`Preview private ${item.title}`}><span className="studio-play-icon" aria-hidden="true">{library === 'recordings' ? '♫' : '▶'}</span><strong>{library === 'recordings' ? 'Listen to protected recording' : 'Preview protected video'}</strong></button>
            : item.preview_url ? <button className="studio-preview-trigger" type="button" onClick={() => setPreview({kind: 'image', url: backendUrl(item.preview_url), title: item.title})} aria-label={`Preview ${item.title}`}><img src={backendUrl(item.preview_url)} loading="lazy" alt="" onError={(event) => { event.currentTarget.hidden = true }} /><span>View image</span></button>
            : item.player_url && safePlayer(item.player_url) ? <button className="studio-preview-trigger studio-play-trigger studio-youtube-cover" type="button" onClick={() => setPreview({kind: 'video', url: safePlayer(item.player_url), title: item.title})} aria-label={`Preview ${item.title}`}>
              {hostedVideoThumbnail(safePlayer(item.player_url)) && !failedThumbnails[item.id] && <img src={hostedVideoThumbnail(safePlayer(item.player_url))} loading="lazy" alt="" referrerPolicy="no-referrer" onError={() => setFailedThumbnails(old => ({...old, [item.id]: true}))}/>}
              <span className="studio-play-icon" aria-hidden="true">▶</span><strong>Watch or preview stream</strong></button>
            : <span className="studio-art-placeholder" aria-hidden="true">{selected?.icon}</span>}
            <small>{library === 'hosted' ? 'YOUTUBE / LIVE' : selected?.name.toUpperCase()} · #{item.id}</small>
          </div>
          <div className="studio-item-body"><div className="studio-item-meta"><span className={'studio-status studio-status-' + item.state}>{item.state}</span>{item.edition && <span>Edition {item.edition}</span>}</div><h3>{item.title}</h3><div className="studio-item-actions">{canPublishImmediately ? <button type="button" disabled={pending !== null} onClick={() => {setItemToPublish(itemToPublish === item.id ? null : item.id); setItemDestinations(['hosted','videos'].includes(library) ? ['foundation_archive'] : []); setItemEdition(item.edition ? String(item.edition) : ''); setItemMediaCategory([...MEDIA_CATEGORIES,...customCollections.map(c => [c.slug,c.title])].some(([key]) => key === item.programme) ? item.programme : 'general'); setItemProgrammeName(item.event || '')}}>{itemToPublish === item.id ? 'Close publishing' : 'Publish to website'}</button> : user.can_manage_catalogue ? <button type="button" disabled={pending !== null} onClick={() => addToFoundation(item)}>Add to Foundation catalogue</button> : null}{canEdit && item.metadata && <button type="button" disabled={pending !== null} onClick={() => setEditing(editing === item.id ? null : item.id)}>{editing === item.id ? 'Cancel edit' : 'Edit details'}</button>}{canDelete && item.state === 'draft' && <button type="button" className="studio-delete-draft" disabled={pending !== null} onClick={() => deleteDraft(item)}>Delete draft</button>}{canPublish && item.state === 'published' && ['photos','videos','hosted','recordings','flyers','promotions','activities'].includes(library) && <button type="button" disabled={pending !== null} onClick={() => publishExisting(item, 'withdraw')}>Withdraw from website</button>}{!canEdit && !canPublish && <span>Read-only catalogue</span>}</div>
          {itemToPublish === item.id && <div className="studio-item-publisher">
            <strong>Where should “{item.title}” appear?</strong>
             {['hosted','videos','recordings'].includes(library) && <><MediaCategoryInput value={itemMediaCategory} onChange={setItemMediaCategory} audio={library === 'recordings'} customCollections={customCollections}/>
               {['ramadan','other'].includes(itemMediaCategory) && <label>Programme / series (optional)<input value={itemProgrammeName} onChange={e=>setItemProgrammeName(e.target.value)} maxLength={150}/></label>}</>}
            <StudioPublishChoices choices={PUBLISH_DESTINATIONS[library] || []} selected={itemDestinations} setSelected={setItemDestinations} authorized={canPublishImmediately} />
            {itemDestinations.some(needsEdition) && <label>Camp edition<select required value={itemEdition} onChange={event => setItemEdition(event.target.value)}>
              <option value="">Choose edition</option>{uploadInfo.editions.map(row => <option key={row.id} value={row.id}>{row.name} ({row.year})</option>)}
            </select></label>}
            <button type="button" disabled={pending !== null || !itemDestinations.length || itemDestinations.some(needsEdition) && !itemEdition} onClick={() => publishExisting(item, 'publish', itemDestinations)}>{pending === item.id ? 'Publishing…' : 'Publish Now'}</button>
          </div>}
          {editing === item.id && <form className="studio-edit-form" onSubmit={event => saveMetadata(event, item)}><strong>Editorial details</strong>{Object.entries(item.metadata || {}).map(([name,value]) => <label key={name}>{name.replaceAll('_',' ')}{typeof value === 'boolean' ? <input name={name} type="checkbox" defaultChecked={value} /> : <input name={name} type={typeof value === 'number' ? 'number' : 'text'} min={typeof value === 'number' ? 0 : undefined} maxLength={typeof value === 'number' ? undefined : 5000} defaultValue={value ?? ''} />}</label>)}<button type="submit" disabled={pending !== null}>Save changes</button></form>}</div>
        </article>)}</div> : <div className="studio-state"><strong>{q || state || edition ? 'No items match these filters.' : `No ${displayName?.toLowerCase()} saved here yet.`}</strong><p>{q || state || edition ? 'Open “Search and filter saved items” to change or clear your filters.' : isHosted ? 'Use “Add video links” above to save your first video or livestream.' : hasUploadForm ? 'When file uploads are activated, you can add new media using the upload action above. Any existing items will appear here.' : 'Speaker appearances will appear here when they are available.'}</p></div>}
        {more && <div className="studio-pagination"><button type="button" disabled={loading || page >= 100} onClick={() => setPage(current => current + 1)}>{loading ? 'Loading…' : 'Load more media'}</button></div>}
      </section>
      <StudioEditorial user={user} onCollectionsChange={() => studioEditorialCollections().then(data => setCustomCollections(data.collections || [])).catch(() => {})} />
      {(user.can_manage_catalogue || user.can_publish_destinations) && <StudioCarouselEditor user={user} editions={uploadInfo.editions} />}
      {(user.can_manage_catalogue || user.can_publish_destinations) ? <details className="studio-advanced-publishing" open={Boolean(focusAsset)} onToggle={event => {if (!event.currentTarget.open && focusAsset) setFocusAsset('')}}><summary>Advanced: manage albums and publishing details</summary><StudioDestinations user={user} editions={uploadInfo.editions} library={library} sourceLinkRefresh={revision} focusAsset={focusAsset} /></details> : null}
      {preview && <div className="studio-preview-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setPreview(null) }}>
        <section className="studio-preview-dialog" role="dialog" aria-modal="true" aria-label={`Preview: ${preview.title}`}>
          <header><div><span className="studio-kicker">MEDIA PREVIEW</span><h2>{preview.title}</h2></div><button type="button" autoFocus onClick={() => setPreview(null)} aria-label="Close media preview">✕</button></header>
          {preview.kind === 'video' ? <><div className="studio-preview-video"><iframe title={preview.title} src={preview.url} allow="encrypted-media; picture-in-picture; fullscreen" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" /></div><p>Player availability depends on the video's YouTube or Vimeo visibility and embedding settings.</p><a href={preview.url} target="_blank" rel="noopener noreferrer">Open video externally ↗</a></>
            : preview.kind === 'private-audio' ? <div className="studio-private-player"><audio controls preload="none" crossOrigin="use-credentials" src={preview.url}>Audio preview is unavailable in this browser.</audio><a href={preview.url + '?download=1'} rel="noreferrer">Download authorized recording</a><small>Staff access is checked by the backend for every request.</small></div>
            : preview.kind === 'private-video' ? <div className="studio-private-player"><video controls playsInline preload="none" crossOrigin="use-credentials" src={preview.url}>Video preview is unavailable in this browser.</video><a href={preview.url + '?download=1'} rel="noreferrer">Download authorized video</a><small>Private video remains inaccessible to the public.</small></div>
            : <img src={preview.url} alt={preview.title} />}
        </section>
      </div>}
      <aside className="studio-storage-note"><strong>Publishing and private storage</strong><p>All library records and publishing actions are authorized by the backend. New uploads are unavailable until owner-approved R2 activation; when activated, all uploads save as drafts.</p></aside>
    </main>
  </div>
}
