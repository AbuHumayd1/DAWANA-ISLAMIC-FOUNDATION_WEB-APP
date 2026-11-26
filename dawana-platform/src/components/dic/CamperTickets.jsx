import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { resolveMediaUrl } from '../../services/mediaUrl'

export default function CamperTickets({item}) {
  const [state,setState]=useState({data:null,error:''})
  const [revision,setRevision]=useState(0)
  useEffect(()=>{
    const controller=new AbortController()
    participantRequest('/tickets/?item_id='+encodeURIComponent(item),undefined,{signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setState({data,error:''})})
      .catch(error=>{if(!controller.signal.aborted)setState({data:null,error:error.message})})
    return ()=>controller.abort()
  },[item,revision])
  const {data,error}=state
  return <section className="cp-card" aria-label="My Tickets & Receipts">
    <h2>My Tickets &amp; Receipts</h2>
    <p>Download your verified registration documents. Your ticket is separate from your Digital ID and participation certificate.</p>
    {error ? <><p role="status">{error}</p><button type="button" onClick={()=>setRevision(n=>n+1)}>Refresh tickets</button></> :
      !data ? <p role="status">Loading tickets…</p> : <>
        <a className="button" href={resolveMediaUrl(data.group_url)}>Download group ticket &amp; receipt (PDF)</a>
        <ul>{data.individuals.map(row=><li key={row.url}><strong>{row.name}</strong>{' — NGN '+row.fee+' '}<a href={resolveMediaUrl(row.url)}>Individual ticket (PDF)</a></li>)}</ul>
      </>}
  </section>
}
