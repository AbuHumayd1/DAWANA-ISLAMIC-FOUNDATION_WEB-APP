import { readApiResponse, readCsrfToken } from './apiResponse.js'

const base = `${(import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')}/dic/studio`
let csrf

async function token() {
  const response = await fetch(`${base}/auth/csrf/`, { credentials: 'include', cache: 'no-store' })
  csrf = await readCsrfToken(response)
}

async function studioRequest(path, { method = 'GET', body, ...options } = {}) {
  if (method !== 'GET' && !csrf) await token()
  const response = await fetch(base + path, {
    ...options, method, credentials: 'include', cache: 'no-store',
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(method !== 'GET' ? { 'X-CSRFToken': csrf } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  return readApiResponse(response)
}

export async function changeStudioPassword(current_password, new_password, confirm_password) {
  await token()
  const apiRoot = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
  const response = await fetch(`${apiRoot}/dic/staff/auth/password/change/`, {
    method: 'POST', credentials: 'include', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
    body: JSON.stringify({ current_password, new_password, confirm_password }),
  })
  return readApiResponse(response)
}

export const studioSession = () => studioRequest('/auth/me/')
export async function studioLogin(username, password) {
  await token()
  const user = await studioRequest('/auth/login/', { method: 'POST', body: { username, password } })
  await token()
  return user
}
export async function studioLogout() {
  await studioRequest('/auth/logout/', { method: 'POST' })
  csrf = undefined
}
export const studioLibrary = ({ library, q, state, edition, page = 1 }) => {
  const params = new URLSearchParams({ library, page: String(page) })
  if (q) params.set('q', q)
  if (state) params.set('state', state)
  if (edition) params.set('edition', edition)
  return studioRequest('/library/?' + params)
}
export const studioPublish = (library, id, action) =>
  studioRequest(`/library/${encodeURIComponent(library)}/${encodeURIComponent(id)}/publication/`, { method: 'POST', body: { action } })

export const studioUploadStatus = () => studioRequest('/uploads/')
export async function studioUpload(library, fields) {
  if (!csrf) await token()
  const body = new FormData()
  body.append('library', library)
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null && value !== '') body.append(key, value)
  }
  const response = await fetch(base + '/uploads/', {
    method: 'POST', body, credentials: 'include', cache: 'no-store',
    headers: { 'X-CSRFToken': csrf },
  })
  return readApiResponse(response)
}

export const studioDeleteDraft = (library, id, confirmHistoricalDeletion = false) =>
  studioRequest(`/library/${encodeURIComponent(library)}/${encodeURIComponent(id)}/draft/`, {
    method: 'DELETE',
    body: { confirm_historical_deletion: confirmHistoricalDeletion },
  })

export const studioEdit = (library, id, metadata) => studioRequest(`/library/${encodeURIComponent(library)}/${encodeURIComponent(id)}/metadata/`, { method: 'PATCH', body: metadata })

export const studioAssets = (page = 1, { kind = '', q = '', album = '' } = {}) => {
  const params = new URLSearchParams({ page: String(page) })
  if (kind) params.set('kind', kind)
  if (q) params.set('q', q)
  if (album) params.set('album', album)
  return studioRequest('/assets/?' + params.toString())
}
export const studioLinkAsset = (source_kind, source_id) =>
  studioRequest('/assets/', { method: 'POST', body: { source_kind, source_id } })
export const studioAssetMetadata = (id, fields) =>
  studioRequest(`/assets/${encodeURIComponent(id)}/`, { method: 'PATCH', body: fields })
export const studioArchiveAsset = (id, action) =>
  studioRequest(`/assets/${encodeURIComponent(id)}/`, { method: 'POST', body: { action } })
export const studioPlacement = (id, destination, action, edition = null) =>
  studioRequest(`/assets/${encodeURIComponent(id)}/placements/`, {
    method: 'POST', body: { destination, action, edition },
  })

export const studioHostedLinks = (items) => studioRequest('/hosted-links/', { method: 'POST', body: { items } })

export const studioEditorialCollections = () => studioRequest('/editorial/collections/')
export const studioCreateCollection = fields =>
  studioRequest('/editorial/collections/', { method: 'POST', body: fields })
export const studioUpdateCollection = (id, fields) =>
  studioRequest('/editorial/collections/' + encodeURIComponent(id) + '/', {
    method: 'PATCH', body: fields,
  })
export const studioEditorialItems = () => studioRequest('/editorial/items/')
export const studioCreateEditorialItem = async (fields, documentFile) => {
  if (!documentFile) return studioRequest('/editorial/items/', { method: 'POST', body: fields })
  if (!csrf) await token()
  const data = new FormData()
  for (const [key, value] of Object.entries(fields)) {
    if (value !== null && value !== undefined) data.append(key, value)
  }
  data.append('document', documentFile)
  const response = await fetch(base + '/editorial/items/', {
    method: 'POST', credentials: 'include', cache: 'no-store',
    headers: { 'X-CSRFToken': csrf }, body: data,
  })
  return readApiResponse(response)
}
export const studioUpdateEditorialItem = (id, fields) =>
  studioRequest('/editorial/items/' + encodeURIComponent(id) + '/', {
    method: 'PATCH', body: fields,
  })
export const studioPublishEditorialItem = (id, action) =>
  studioRequest('/editorial/items/' + encodeURIComponent(id) + '/', {
    method: 'POST', body: { action },
  })

export const studioDeleteEditorialDraft = id =>
  studioRequest('/editorial/items/' + encodeURIComponent(id) + '/', { method: 'DELETE' })

export const studioCarousels = () => studioRequest('/carousels/')
export const studioCreateCarousel = fields => studioRequest('/carousels/', { method: 'POST', body: fields })
export const studioUpdateCarousel = (id, fields) => studioRequest('/carousels/' + encodeURIComponent(id) + '/', {method: 'PATCH', body: fields})
export const studioActOnCarousel = (id, fields) => studioRequest('/carousels/' + encodeURIComponent(id) + '/', {method: 'POST', body: fields})
export async function studioUploadCarouselAudio(id, file, loopAudio = false) {
  if (!csrf) await token()
  const body = new FormData()
  body.append('soundtrack', file)
  body.append('loop_audio', loopAudio ? 'true' : 'false')
  const response = await fetch(base + '/carousels/' + encodeURIComponent(id) + '/', {
    method: 'PATCH', body, credentials: 'include', cache: 'no-store',
    headers: {'X-CSRFToken': csrf},
  })
  return readApiResponse(response)
}

export const studioLecturerAppearances = (page = 1) =>
  studioRequest('/lecturer-appearances/?page=' + encodeURIComponent(page))
export const studioCreateLecturerAppearance = fields =>
  studioRequest('/lecturer-appearances/', { method: 'POST', body: fields })
export const studioEditLecturerAppearance = (id, fields) =>
  studioRequest('/lecturer-appearances/' + encodeURIComponent(id) + '/', { method: 'PATCH', body: fields })
export const studioActOnLecturerAppearance = (id, action) =>
  studioRequest('/lecturer-appearances/' + encodeURIComponent(id) + '/', { method: 'POST', body: { action } })

async function lecturerFormRequest(path, method, fields = {}) {
  if (!csrf) await token()
  const data = new FormData()
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null && value !== '') data.append(key, value)
  }
  const response = await fetch(base + path, {
    method, body: method === 'DELETE' ? undefined : data,
    credentials: 'include', cache: 'no-store', headers: { 'X-CSRFToken': csrf },
  })
  return readApiResponse(response)
}
export const studioAddSimpleLecturer = fields =>
  lecturerFormRequest('/simple-lecturers/', 'POST', fields)
export const studioUpdateSimpleLecturer = (id, fields) =>
  lecturerFormRequest('/simple-lecturers/' + encodeURIComponent(id) + '/', 'PATCH', fields)
export const studioDeleteSimpleLecturer = id =>
  lecturerFormRequest('/simple-lecturers/' + encodeURIComponent(id) + '/', 'DELETE')

// User-facing removal retains private source media and audit history.
export const studioRemoveMedia = (library, id) =>
  studioRequest('/library/' + encodeURIComponent(library) + '/' + encodeURIComponent(id) + '/remove/', {
    method: 'POST', body: {},
  })

 
// A retained ticket resumes the same transfer, including after a lost finish response.
// No automatic retry of an ordinary non-idempotent publishing request.
const videoTransfers = new Map()
export async function studioDirectVideo(fields, onProgress, owner, collection='videos') {
  const file = collection === 'promotions' ? fields.video : fields.recording_file
  if (!file || !(collection === 'promotions' ? /\.(mp4|mov)$/i : /\.(mp4|webm|mov)$/i).test(file.name) || file.size <= 0 || file.size > 1024*1024*1024)
    throw new Error('Choose a supported video of at most 1 GB.')
  const key = JSON.stringify([owner,collection,file.name,file.size,file.lastModified])
  let transfer = videoTransfers.get(key)
  if (!transfer) {
    transfer = await studioRequest('/video-transfer/', {method:'POST',body:{action:'start',collection,name:file.name,size:file.size}})
    videoTransfers.set(key,transfer)
  }
  const {ticket,part_size} = transfer
  const action = (name, extra={}) => studioRequest('/video-transfer/',{method:'POST',body:{action:name,collection,ticket,...extra}})
  const {parts} = await action('status')
  const completed = new Set(parts)
  const count = Math.ceil(file.size/part_size)
  let sent = parts.reduce((sum,n)=>sum+Math.min(part_size,file.size-(n-1)*part_size),0)
  onProgress(Math.floor(100*sent/file.size),'Uploading video')
  for (let number=1;number<=count;number++) {
    if(completed.has(number)) continue
    const chunk=file.slice((number-1)*part_size,number*part_size)
    let done=false
    for(let attempt=0;attempt<3&&!done;attempt++){
      try {
        const {url}=await action('part',{number})
        await new Promise((resolve,reject)=>{
          const xhr=new XMLHttpRequest()
          xhr.open('PUT',url)
          xhr.timeout=180000
          xhr.upload.onprogress=e=>onProgress(Math.min(99,Math.floor(100*(sent+e.loaded)/file.size)),'Uploading video')
          xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve():reject(new Error('Video part rejected by storage.'))
          xhr.onerror=xhr.ontimeout=xhr.onabort=()=>reject(new Error('Video connection interrupted.'))
          xhr.send(chunk)
        })
        done=true
      }catch(error){if(attempt===2)throw new Error('Video transfer interrupted. Keep this form open and retry to resume completed parts.')}
    }
    sent+=chunk.size
    onProgress(Math.floor(100*sent/file.size),'Uploading video')
  }
  onProgress(100,'Verifying video and saving draft')
  await token()
  const data=new FormData()
  data.append('collection',collection);data.append('action','finish');data.append('ticket',ticket)
  for(const [name,value] of Object.entries(fields)){
    if(!['recording_file','video'].includes(name)&&value!==undefined&&value!==null)data.append(name,value)
  }
  const response=await fetch(base+'/video-transfer/',{method:'POST',credentials:'include',cache:'no-store',headers:{'X-CSRFToken':csrf},body:data})
  const result=await readApiResponse(response)
  return result
}
