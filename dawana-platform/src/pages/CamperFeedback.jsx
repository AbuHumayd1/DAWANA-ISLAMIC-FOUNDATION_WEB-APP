import CamperSelect from '../components/dic/CamperSelect'
import { PortalIcon } from '../components/dic/CamperExperience'
import CamperBrand from '../components/dic/CamperBrand'
import { useEffect,useRef,useState } from 'react'
import { Link } from 'react-router-dom'
import { participantRequest } from '../services/participantApi'
import { WelfareForm } from '../components/operations/FeedbackForms'
import ExperienceForm from '../components/dic/CamperExperienceForm'
import { FeedbackWelcome, FeedbackChannelNav } from '../components/dic/CamperFeedbackLayout'
import './Feedback.css'
import { useSearchParams } from 'react-router-dom'
import { participantSessionClosed,subscribeParticipantSessionClosed } from '../services/participantSession'

export default function CamperFeedback() {
  const [params,setParams]=useSearchParams()
  const [theme] = useState(() => {
    try { return window.localStorage.getItem('dic-camper-appearance') === 'dark' ? 'dark' : 'light' } catch { return 'light' }
  })
  const [state,setState]=useState({data:null,error:''}), [itemId,setItemId]=useState('')
  const channel = ['daily','final','welfare','history'].includes(params.get('channel')) ? params.get('channel') : 'daily'
  const chooseChannel = next => setParams(previous => { const updated = new URLSearchParams(previous); updated.set('channel',next); return updated })
  const transport = useRef(null)
  useEffect(()=>{const controller=new AbortController();transport.current=controller;let timer;const expire=()=>{controller.abort();setState({data:null,error:'Participant access has closed or expired. Verify again.'});setItemId('')};const unsubscribe=subscribeParticipantSessionClosed(expire);window.addEventListener('participant-session-expired',expire);if(participantSessionClosed()){Promise.resolve().then(expire)}else participantRequest('/feedback/options/',undefined,{signal:controller.signal}).then(data=>{if(controller.signal.aborted)return;setState({data,error:''});timer=setTimeout(expire,Math.max(0,new Date(data.expires_at).getTime()-Date.now()))}).catch(error=>{if(!controller.signal.aborted)setState({data:null,error:error.message})});return()=>{controller.abort();clearTimeout(timer);unsubscribe();window.removeEventListener('participant-session-expired',expire)}},[])
  useEffect(() => { if (state.data?.items?.length === 1) setItemId(String(state.data.items[0].id)) }, [state.data])
  const data=state.data, item=data?.items.find(row=>String(row.id)===itemId)
  return <div className="camper-feedback-shell cp-experience" data-theme={theme}><div className="cf-portal-bar"><Link to="/dic/participant?view=explore" className="cf-portal-brand" aria-label="Back to DIC Camper World"><CamperBrand /></Link><Link to="/dic/participant?view=explore" className="cf-portal-explore"><PortalIcon name="explore" /><span>Explore</span></Link></div><div className="camper-feedback cw-feedback-page"><Link className="cf-back-link" to="/dic/participant">← Back to Camper World</Link><FeedbackWelcome channel={channel} /><FeedbackChannelNav channel={channel} onChange={chooseChannel} /><p className="cf-safety-note">For urgent health or safety concerns, contact an available camp official immediately.</p>
    {state.error?<p role="alert">{state.error}</p>:!data?<p role="status">Loading your verified booking…</p>:<>
      <details className="cf-privacy"><summary>Privacy & help with feedback</summary><p>{data.privacy}</p><p>A guardian may help a younger camper enter the camper’s own answers. Complaints are identified and confidential, separate from anonymous feedback.</p></details>
      <div className="feedback-controls">{data.items.length > 1 ? <CamperSelect label="Camper and edition" value={itemId} onChange={setItemId} options={data.items.map(row => ({ value: String(row.id), label: row.name + ' — ' + row.edition_name }))} /> : data.items.length === 1 ? <div className="cf-single-camper"><span>Camper and edition</span><strong>{data.items[0].name} — {data.items[0].edition_name}</strong></div> : null}</div>
      {!data.items.length&&<p>No participants are available in this verified booking session.</p>}
      {item&&(['daily','final'].includes(channel)?<>
        {channel==='daily'&&(data.today<item.start||data.today>item.end)?<p>Daily feedback is available only during camp, on that same camp date.</p>:channel==='final'&&data.today<item.end?<p>Final evaluation opens on the final camp date.</p>:<ExperienceForm key={channel+'-'+itemId} channel={channel} spec={item.questions[channel]} ratings={item.questions[channel].scale || data.ratings} today={data.today} start={item.start} end={item.end} onSave={payload=>participantRequest('/feedback/',{...payload,item_id:item.id},{signal:transport.current?.signal})}/>}
      </>:channel==='welfare'?(data.today<item.start||data.today>item.end?<p>Complaints can be submitted during camp. Contact camp officials for assistance.</p>:<WelfareForm key={itemId} categories={data.categories} urgent={data.urgent} reporterNotice="The selected camper is the affected person. This complaint is identified through your authorized booking." onSave={payload=>participantRequest('/welfare/',{...payload,item_id:item.id},{signal:transport.current?.signal})}/>):<ComplaintHistory key={itemId} itemId={item.id}/>)}

    </>}
  </div><nav className="cf-portal-bottom" aria-label="Camper navigation">
    {[['home','Home','/dic/participant'],['day','My Day','/dic/participant?view=day'],['arena','Arena','/dic/participant?view=arena'],['explore','Explore','/dic/participant?view=explore'],['me','Me','/dic/participant?view=me']].filter(([key]) => key !== 'arena' || item?.registration_basis !== 'tutor').map(([key,label,to]) => <Link key={key} to={to} aria-current={key === 'explore' ? 'page' : undefined}><PortalIcon name={key}/><span>{label}</span></Link>)}
  </nav></div>
}

function ComplaintHistory({itemId}) {
  const [state,setState]=useState({loading:true,rows:[],error:''}),[revision,setRevision]=useState(0)
  useEffect(()=>{const controller=new AbortController();participantRequest('/welfare/?item_id='+itemId,undefined,{signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setState({loading:false,rows:data.results,error:''})}).catch(error=>{if(!controller.signal.aborted)setState({loading:false,rows:[],error:error.message})});return()=>controller.abort()},[itemId,revision])
  return <section aria-label="My complaints"><h2>My Complaints / Complaint Status</h2><button onClick={()=>setRevision(value=>value+1)}>Refresh</button>{state.loading?<p role="status">Loading complaints...</p>:state.error?<p role="alert">{state.error}</p>:!state.rows.length?<p>No complaints for this camper.</p>:state.rows.map(row=><article className="ops-panel" key={row.id}><h3>{row.category} / {row.status_label}</h3><p>{row.urgency==='urgent'?'Urgent':'Normal'} / {row.time}</p><p className="welfare-private">{row.description}</p></article>)}</section>
}
