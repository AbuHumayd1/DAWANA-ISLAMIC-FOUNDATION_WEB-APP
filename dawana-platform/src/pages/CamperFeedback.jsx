import { useEffect,useRef,useState } from 'react'
import { Link } from 'react-router-dom'
import { participantRequest } from '../services/participantApi'
import { ExperienceForm, WelfareForm } from '../components/operations/FeedbackForms'
import './Feedback.css'
import { useSearchParams } from 'react-router-dom'
import { participantSessionClosed,subscribeParticipantSessionClosed } from '../services/participantSession'

export default function CamperFeedback() {
  const [params]=useSearchParams()
  const [state,setState]=useState({data:null,error:''}), [itemId,setItemId]=useState(''), [channel,setChannel]=useState(['daily','final','welfare','history'].includes(params.get('channel'))?params.get('channel'):'daily')
  const transport = useRef(null)
  useEffect(()=>{const controller=new AbortController();transport.current=controller;let timer;const expire=()=>{controller.abort();setState({data:null,error:'Participant access has closed or expired. Verify again.'});setItemId('')};const unsubscribe=subscribeParticipantSessionClosed(expire);window.addEventListener('participant-session-expired',expire);if(participantSessionClosed()){Promise.resolve().then(expire)}else participantRequest('/feedback/options/',undefined,{signal:controller.signal}).then(data=>{if(controller.signal.aborted)return;setState({data,error:''});timer=setTimeout(expire,Math.max(0,new Date(data.expires_at).getTime()-Date.now()))}).catch(error=>{if(!controller.signal.aborted)setState({data:null,error:error.message})});return()=>{controller.abort();clearTimeout(timer);unsubscribe();window.removeEventListener('participant-session-expired',expire)}},[])
  const data=state.data, item=data?.items.find(row=>String(row.id)===itemId)
  return <main className="camper-feedback"><h1>Camp feedback</h1><p><Link to="/dic/participant">Open or verify your participant / guardian session</Link></p><p>For urgent health or safety concerns, contact an available camp official immediately.</p>
    {state.error?<p role="alert">{state.error}</p>:!data?<p role="status">Loading your verified booking…</p>:<>
      <p>{data.privacy}</p><p>A guardian may help a younger camper enter the camper’s own answers. Complaints are identified and confidential, separate from anonymous feedback.</p>
      <div className="feedback-controls"><label>Camper and edition<select value={itemId} onChange={event=>setItemId(event.target.value)}><option value="">Choose a camper</option>{data.items.map(row=><option value={row.id} key={row.id}>{row.name} — {row.edition_name}</option>)}</select></label>
        <label>Channel<select value={channel} onChange={event=>setChannel(event.target.value)}><option value="daily">Daily Camper Feedback</option><option value="final">Final Camp Evaluation</option><option value="welfare">Submit a Complaint</option><option value="history">My Complaints / Complaint Status</option></select></label></div>
      {!data.items.length&&<p>No participants are available in this verified booking session.</p>}
      {item&&(['daily','final'].includes(channel)?<>
        {channel==='daily'&&(data.today<item.start||data.today>item.end)?<p>Daily feedback is available only during camp, on that same camp date.</p>:channel==='final'&&data.today<item.end?<p>Final evaluation opens on the final camp date.</p>:<ExperienceForm key={channel+'-'+itemId} channel={channel} spec={item.questions[channel]} ratings={data.ratings} today={data.today} start={item.start} end={item.end} onSave={payload=>participantRequest('/feedback/',{...payload,item_id:item.id},{signal:transport.current?.signal})}/>}
      </>:channel==='welfare'?(data.today<item.start||data.today>item.end?<p>Complaints can be submitted during camp. Contact camp officials for assistance.</p>:<WelfareForm key={itemId} categories={data.categories} urgent={data.urgent} reporterNotice="The selected camper is the affected person. This complaint is identified through your authorized booking." onSave={payload=>participantRequest('/welfare/',{...payload,item_id:item.id},{signal:transport.current?.signal})}/>):<ComplaintHistory key={itemId} itemId={item.id}/>)}

    </>}
  </main>
}

function ComplaintHistory({itemId}) {
  const [state,setState]=useState({loading:true,rows:[],error:''}),[revision,setRevision]=useState(0)
  useEffect(()=>{const controller=new AbortController();participantRequest('/welfare/?item_id='+itemId,undefined,{signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setState({loading:false,rows:data.results,error:''})}).catch(error=>{if(!controller.signal.aborted)setState({loading:false,rows:[],error:error.message})});return()=>controller.abort()},[itemId,revision])
  return <section aria-label="My complaints"><h2>My Complaints / Complaint Status</h2><button onClick={()=>setRevision(value=>value+1)}>Refresh</button>{state.loading?<p role="status">Loading complaints...</p>:state.error?<p role="alert">{state.error}</p>:!state.rows.length?<p>No complaints for this camper.</p>:state.rows.map(row=><article className="ops-panel" key={row.id}><h3>{row.category} / {row.status_label}</h3><p>{row.urgency==='urgent'?'Urgent':'Normal'} / {row.time}</p><p className="welfare-private">{row.description}</p></article>)}</section>
}
