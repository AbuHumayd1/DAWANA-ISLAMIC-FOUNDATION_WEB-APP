import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { resolveMediaUrl } from '../../services/mediaUrl'
export default function CamperResources({ item, certificateOnly = false }) {
  const [state,setState]=useState({item:null,data:null,error:''}),[revision,setRevision]=useState(0)
  useEffect(()=>{ const controller=new AbortController();participantRequest(`/resources/?item_id=${item}`,undefined,{signal:controller.signal})
    .then(data=>{if(!controller.signal.aborted)setState({item,data,error:''})}).catch(error=>{if(!controller.signal.aborted)setState({item,data:null,error:error.message})});return()=>controller.abort()
  },[item,revision])
  const data=state.item===item?state.data:null
  if(state.item===item&&state.error)return <section role="alert"><p>{state.error}</p><button onClick={()=>setRevision(v=>v+1)}>Try again</button></section>
  if(!data)return <p role="status">Loading camp resources…</p>
  return <section className="cp-card"><h2>{certificateOnly?'Participation certificate':'Lecture Recordings'}</h2>
    {!certificateOnly&&<>{!data.recordings.length&&<p>Published recordings will appear here.</p>}{data.recordings.map(row=><article className="cp-recording" key={`${row.kind}-${row.id}`}><h3>{row.title}</h3><p>{row.lecturer}</p>{row.session&&<small>{row.session}</small>}<p>{row.description}</p><audio crossOrigin="use-credentials" controls preload="none" src={resolveMediaUrl(row.url)} aria-label={'Play ' + row.title}/><a href={resolveMediaUrl(row.url+'&download=1')}>Download audio</a></article>)}</>}
    {certificateOnly&&(data.certificate.available?<a className="button" href={resolveMediaUrl(data.certificate.url)}>Download my certificate (PDF)</a>:<p>Your certificate will be available after the approved release.</p>)}
  </section>
}
