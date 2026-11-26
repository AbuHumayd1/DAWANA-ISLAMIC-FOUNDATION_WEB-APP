import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { resolveMediaUrl } from '../../services/mediaUrl'
import './CamperTickets.css'

const money = value => new Intl.NumberFormat('en-NG', {style:'currency',currency:'NGN'}).format(Number(value))
function TicketIcon() {return <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 6h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4zM15 6v3m0 2v2m0 2v3"/></svg>}
function DownloadIcon() {return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></svg>}

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
  const group=data?.individuals.length>1
  return <section className="cp-card cp-ticket-wallet" aria-label="My Tickets & Receipts">
    <header className="cp-ticket-heading"><span className="cp-ticket-icon"><TicketIcon/></span><div><h2>My Tickets &amp; Receipts</h2><p>Your official camp admission documents.</p></div></header>
    {error ? <><p role="status">{error}</p><button type="button" onClick={()=>setRevision(n=>n+1)}>Refresh tickets</button></> :
      !data ? <p role="status">Loading tickets…</p> : <>
        <div className="cp-ticket-summary"><div><span>{group?'Total paid':'Amount paid'}</span><strong>{money(data.total)}</strong></div><span className="cp-ticket-verified">✓ Payment verified</span></div>
        {group && <a className="button cp-ticket-download" href={resolveMediaUrl(data.group_url)}><DownloadIcon/> Group ticket &amp; receipt (PDF)</a>}
        <div className="cp-ticket-list">{data.individuals.map(row=><article className="cp-ticket-entry" key={row.url}><div className="cp-ticket-entry-info"><span className="cp-ticket-kicker">DIC admission ticket</span><h3>{row.name}</h3><p>{row.category}{row.category?' · ':''}{money(row.fee)}</p><small>{row.reference}</small></div><a className="button cp-ticket-download" href={resolveMediaUrl(row.url)}><DownloadIcon/>{group?'Individual ticket (PDF)':'Ticket & receipt (PDF)'}</a></article>)}</div>
        <p className="cp-ticket-note">Present your ticket at arrival. Your Digital ID and participation certificate remain separate.</p>
      </>}
  </section>
}
