import { useEffect, useState } from 'react'
import { studioAssets, studioCarousels, studioCreateCarousel, studioUpdateCarousel,
  studioActOnCarousel, studioUploadCarouselAudio, studioUpload, studioPublish, studioLinkAsset } from '../services/mediaStudioApi'
import './StudioCarouselEditor.css'

const destinations = [
  ['foundation_home', 'Foundation homepage'], ['foundation_archive', 'Foundation Media page'],
  ['dic_landing', 'DIC landing page'], ['dic_memories', 'DIC Camp Scrapbook'],
]

export default function StudioCarouselEditor({user, editions=[]}) {
  const [list, setList] = useState([])
  const [assets, setAssets] = useState([])
  const [selected, setSelected] = useState('')
  const [format, setFormat] = useState('images')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [slides, setSlides] = useState([])
  const [dest, setDest] = useState([])
  const [edition, setEdition] = useState('')
  const [audioFile, setAudioFile] = useState(null)
  const [newImages, setNewImages] = useState([])
  const [newImageEdition, setNewImageEdition] = useState('')
  const [newImageTitle, setNewImageTitle] = useState('')
  const [librarySearch, setLibrarySearch] = useState('')
  const [loopAudio, setLoopAudio] = useState(false)
  const [soundtrackOnVideos, setSoundtrackOnVideos] = useState(false)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let cancelled = false
    Promise.all([studioCarousels(),studioAssets(1)]).then(([data, catalogue]) => {
      if (!cancelled) {setList(data.carousels || []);setAssets(catalogue.assets || [])}
    }).catch(error => {if (!cancelled) setMessage(error.message)})
    return () => {cancelled = true}
  }, [reload])
  const current = list.find(item=>item.id===selected)
  const isDraft = !current || current.state !== 'published'
  const choices = assets.filter(asset => !asset.archived &&
    (format === 'images' ? ['photos','flyers','activities','appearances'].includes(asset.source_kind)
      : format === 'videos' ? ['hosted','videos','promotions'].includes(asset.source_kind)
        : ['photos','flyers','activities','appearances','hosted','videos','promotions'].includes(asset.source_kind)))
  const canManage = user.can_manage_catalogue || user.can_publish_destinations
  const imageChoices = choices.filter(a => !slides.some(s => s.asset_id === a.id) &&
    (!librarySearch.trim() || (a.title + ' ' + a.source_id).toLowerCase().includes(librarySearch.toLowerCase())))
  async function uploadNewImages(event) {
    event.preventDefault()
    if (!newImages.length) return setMessage('Choose at least one image.')
    if (!newImageEdition) return setMessage('Choose a camp year.')
    if (!canManage || format === 'videos') return setMessage('Choose image or mixed-media carousel first.')
    if (newImages.length + slides.length > 40) return setMessage('A carousel supports up to 40 cards.')
    setBusy(true); setMessage('')
    let completed = 0
    const added = []
    try {
      for (const file of newImages) {
        const caption = (newImageTitle.trim() || file.name.replace(/\.[^.]+$/, '').replace(/[_-]/g,' ') || 'Camp photograph').slice(0,300)
        const created = await studioUpload('photos', {
          edition: newImageEdition, caption,
          alt_text: 'Camp photograph: ' + caption.slice(0,200), photograph: file,
        })
        // A published image is required before it is eligible for a carousel.
        await studioPublish('photos', created.id, 'publish')
        const linked = await studioLinkAsset('photos', created.id)
        if (!linked?.asset?.id) throw new Error('Image was uploaded but could not be added to the carousel library.')
        const asset = linked.asset
        added.push({ asset_id: asset.id, caption: '', title: asset.title })
        completed++
      }
      setSlides(current => [...current, ...added])
      setAssets(old => [...added.map((row, index) => ({
        id: row.asset_id, title: row.title, source_kind: 'photos',
        source_id: 'new-' + index, archived: false,
      })), ...old])
      setNewImages([]); setNewImageTitle('')
      setMessage(completed + ' image(s) uploaded and added to this carousel. Select where to publish below.')
    } catch (error) {
      if (added.length) {
        setSlides(current => [...current, ...added])
        setAssets(old => [...added.map((row, index) => ({
          id: row.asset_id, title: row.title, source_kind: 'photos',
          source_id: 'new-' + index, archived: false,
        })), ...old])
      }
      setMessage(completed
        ? completed + ' image(s) added. The remaining upload was interrupted: ' + error.message + '. Check the library before retrying to avoid duplicates.'
        : 'Could not add the image. ' + error.message)
    } finally { setBusy(false) }
  }
  function load(item) {
    setSelected(item?.id || '')
    setFormat(item?.format || 'images')
    setTitle(item?.title || '')
    setDescription(item?.description || '')
    setSlides(item?.slides?.map(s=>({asset_id:s.asset_id,caption:s.caption||'',title:s.title})) || [])
    setDest(item?.destinations?.map(d=>d.destination) || [])
    setEdition(String(item?.destinations?.find(d=>d.edition)?.edition || ''))
    setLoopAudio(Boolean(item?.loop_audio))
    setSoundtrackOnVideos(Boolean(item?.soundtrack_on_videos))
    setAudioFile(null);setMessage('')
  }
  function addAsset(id) {
    if (!id || slides.some(item=>item.asset_id===id)) return
    const asset=assets.find(item=>item.id===id)
    if (asset && slides.length < 40) setSlides(current=>[...current,{asset_id:id,caption:'',title:asset.title}])
  }
  function move(index,delta) {
    const target=index+delta
    if (target<0||target>=slides.length)return
    setSlides(current=>{const copy=[...current];[copy[index],copy[target]]=[copy[target],copy[index]];return copy})
  }
  async function run(action) {
    setBusy(true);setMessage('')
    try {
      const result=await action()
      setMessage('Publication updated.')
      setReload(value=>value+1)
      if(result?.carousel?.id)setSelected(result.carousel.id)
      return result
    } catch(error){setMessage(error.message);return null}
    finally{setBusy(false)}
  }
  async function publish() {
    if (!title.trim()) return setMessage('Enter a carousel title.')
    if (slides.length < 2) return setMessage('Add at least two images or videos.')
    if (format === 'mixed' && (!slides.some(s => ['hosted','videos','promotions'].includes(
      assets.find(a => a.id === s.asset_id)?.source_kind))
      || !slides.some(s => ['photos','flyers','activities','appearances'].includes(
      assets.find(a => a.id === s.asset_id)?.source_kind)))) {
      return setMessage('A mixed carousel needs at least one image and one video.')
    }
    if (!dest.length) return setMessage('Choose where the carousel should appear.')
    if (dest.some(d => d.startsWith('dic_')) && !edition) return setMessage('Choose the DIC camp year.')
    if (!window.confirm('Publish this carousel to the selected website sections?')) return
    setBusy(true); setMessage('')
    let id = current?.id
    try {
      if (!id) id = (await studioCreateCarousel({title, format})).carousel.id
      await studioUpdateCarousel(id, {
        title, description, slides: slides.map(({asset_id,caption})=>({asset_id,caption})),
        loop_audio: loopAudio, soundtrack_on_videos: soundtrackOnVideos,
      })
      if (audioFile) await studioUploadCarouselAudio(id, audioFile, loopAudio)
      await studioActOnCarousel(id, {action:'publish', destinations:dest.map(d=>({
        destination:d, edition:d.startsWith('dic_')?Number(edition):null,
      }))})
      setSelected(id);setReload(n=>n+1)
      setMessage('Carousel published successfully.')
    } catch (error) {
      if (id) {setSelected(id);setReload(n=>n+1)}
      setMessage((id ? 'The carousel is saved but not published. ' : '') +
        (error.message || 'Please check the details and try again.'))
    } finally {setBusy(false)}
  }
  return <section className="studio-carousel-editor" aria-labelledby="studio-carousel-heading">
    <header><span className="studio-kicker">MULTIMEDIA PUBLISHING</span><h2 id="studio-carousel-heading">Carousel Library</h2>
      <p>Combine existing approved media into image, video or mixed-media stories. Each group is one publication.</p></header>
    {message && <p role="status" className="studio-carousel-notice">{message}</p>}
    <div className="studio-carousel-shell">
      <aside className="studio-carousel-list" aria-label="Saved carousels">
        <button type="button" onClick={()=>load(null)}>+ New carousel</button>
        {list.map(item=><button key={item.id} type="button" aria-pressed={item.id===selected} onClick={()=>load(item)}>
          <strong>{item.title}</strong><small>{item.format} · {item.state}</small></button>)}
      </aside>
      <div className="studio-carousel-form">
        <label>Publication format
          <select disabled={Boolean(current)} value={format} onChange={e=>{setFormat(e.target.value);setSlides([])}}>
            <option value="images">Image carousel</option><option value="videos">Video carousel</option>
            <option value="mixed">Mixed media carousel</option>
          </select>
        </label>
        <label>Publication title<input value={title} onChange={e=>setTitle(e.target.value)} maxLength={300} disabled={!isDraft}/></label>
        <label>Full publication caption<textarea rows={3} maxLength={5000} value={description} onChange={e=>setDescription(e.target.value)} disabled={!isDraft}/></label>
        <fieldset disabled={!isDraft}>
          <legend>Carousel cards — {slides.length} / 40</legend>
          {format !== 'videos' && <form className="studio-carousel-direct-upload" onSubmit={uploadNewImages}>
            <strong>Upload new images</strong>
            <label>Choose image files (up to 40)
              <input type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy}
                onChange={e=>setNewImages(Array.from(e.target.files||[]))}/>
            </label>
            <label>Camp year
              <select value={newImageEdition} required disabled={busy} onChange={e=>setNewImageEdition(e.target.value)}>
                <option value="">Choose year</option>
                {editions.map(item=><option key={item.id} value={item.id}>{item.name} ({item.year})</option>)}
              </select>
            </label>
            <label>Title for uploaded images (optional)
              <input value={newImageTitle} onChange={e=>setNewImageTitle(e.target.value)}
                maxLength={300} placeholder="Defaults to the filename"/>
            </label>
            <button disabled={busy || !canManage || !newImages.length || !newImageEdition} type="submit">
              {busy ? 'Adding images…' : 'Add images to carousel'}
            </button>
          </form>}
          <label>Or use an image already uploaded
            <input type="search" aria-label="Search existing media" value={librarySearch}
              placeholder="Search by title or image number" onChange={e=>setLibrarySearch(e.target.value)}/>
          </label>
          <select aria-label="Add existing media card" defaultValue="" onChange={e=>{addAsset(e.target.value);e.target.value=''}}>
            <option value="">Choose an existing image</option>
            {imageChoices.map(a=><option key={a.id} value={a.id}>{a.title} — {a.source_kind} #{a.source_id}</option>)}
          </select>
          {slides.map((item,i)=><div className="studio-carousel-slide" key={item.asset_id}>
            <strong>{i+1}. {item.title}</strong>
            <input aria-label={`Caption for card ${i+1}`} maxLength={300} placeholder="Optional slide caption" value={item.caption}
              onChange={e=>setSlides(prev=>prev.map((s,j)=>j===i?{...s,caption:e.target.value}:s))}/>
            <div><button type="button" disabled={i===0} onClick={()=>move(i,-1)}>↑</button>
            <button type="button" disabled={i===slides.length-1} onClick={()=>move(i,1)}>↓</button>
            <button type="button" onClick={()=>setSlides(prev=>prev.filter((_,j)=>i!==j))}>Remove</button></div>
          </div>)}
        </fieldset>
        <fieldset disabled={!isDraft}><legend>Background audio (optional)</legend>
          <label>Upload MP3, OGG or WAV (up to 12 MB)
            <input type="file" accept=".mp3,.ogg,.wav,audio/mpeg,audio/ogg,audio/wav" onChange={e=>setAudioFile(e.target.files?.[0]||null)} />
          </label>
          <label><input type="checkbox" checked={loopAudio} onChange={e=>setLoopAudio(e.target.checked)}/> Loop soundtrack</label>
          {format !== 'images' && <label><input type="checkbox" checked={soundtrackOnVideos} onChange={e=>setSoundtrackOnVideos(e.target.checked)}/> Play soundtrack over muted uploaded promo video clips</label>}
          {current?.has_audio && <p>Soundtrack saved. Audio starts only when a visitor chooses to play it.</p>}
        </fieldset>
        
        <fieldset><legend>Where should this appear?</legend>
          {destinations.map(([key,label])=><label key={key}><input type="checkbox" checked={dest.includes(key)} onChange={e=>setDest(current=>e.target.checked?[...current,key]:current.filter(d=>d!==key))}/>{label}</label>)}
          {dest.some(d=>d.startsWith('dic_'))&&<label>Camp edition
            <select value={edition} onChange={e=>setEdition(e.target.value)}><option value="">Select edition</option>
            {editions.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        </fieldset>
        <div className="studio-carousel-actions">
          {isDraft && user.can_publish_destinations && <button type="button" disabled={busy||!canManage} onClick={publish}>{busy ? 'Publishing…' : 'Publish carousel'}</button>}
          {current && current.state==='published' && user.can_publish_destinations && <button type="button" disabled={busy}
            onClick={()=>run(()=>studioActOnCarousel(current.id,{action:'withdraw'}))}>Withdraw publication</button>}
          {current && user.can_publish_destinations && <button type="button" className="danger" disabled={busy} onClick={()=>{
            if(window.confirm('Delete this carousel from all website destinations? Source media files and audit history will be retained.')) {
              run(()=>studioActOnCarousel(current.id,{action:'delete'})).then(result=>{if(result){load(null)}})
            }
          }}>Delete publication</button>}
        </div>
      </div>
    </div>
  </section>
}
