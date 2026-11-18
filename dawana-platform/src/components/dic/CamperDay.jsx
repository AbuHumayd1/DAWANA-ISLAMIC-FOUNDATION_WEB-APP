import { useEffect,useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { timetablePath } from '../../services/timetables'
export default function CamperDay({item,compact=false}){
 const [state,setState]=useState({item:null,data:null,error:''}),[tick,setTick]=useState(0)
 useEffect(()=>{const timer=setInterval(()=>setTick(v=>v+1),30000);return()=>clearInterval(timer)},[])
 useEffect(()=>{const controller=new AbortController();Promise.all(['activities','food'].map(type=>participantRequest(timetablePath(item,type),undefined,{signal:controller.signal})))
 .then(data=>{if(!controller.signal.aborted)setState({item,data,error:''})}).catch(error=>{if(!controller.signal.aborted)setState({item,data:null,error:error.message})});return()=>controller.abort()},[item,tick])
 if(state.item===item&&state.error)return <p role="alert">{state.error}<button onClick={()=>setTick(v=>v+1)}>Retry</button></p>
 if(state.item!==item||!state.data)return <p role="status">Loading your day…</p>
 const [programme,food]=state.data
 const upcoming=programme.camp_state==='upcoming',completed=programme.camp_state==='completed'
 const noPublishedEntries = !programme.entries.length && !food.entries.length
 return <section className="cp-day-summary">
 {upcoming ? <div className="cp-day-arrival" role="status">
   <div className="cp-day-arrival-header"><span className="cp-day-arrival-kicker">DIC 2026 · YOUR CAMP COMPANION</span><span className="cp-day-arrival-seal" aria-hidden="true">✧</span></div>
   <div className="cp-day-arrival-content"><div><p className="cp-day-arrival-label">THE COUNTDOWN IS ON</p><h2>Every great day<br />starts here.</h2><p>Your personal camp programme will come alive when camp begins. Everything approved for your day will appear here automatically.</p></div><div className="cp-day-arrival-date"><span>DEC</span><strong>23</strong><small>2026</small></div></div>
   <div className="cp-day-arrival-meta"><span>✦ Your daily programme</span><span>✦ Meals &amp; timings</span><span>✦ Published updates</span></div>
 </div> : <div className="cp-day-overview"><span className="cp-day-symbol" aria-hidden="true">▦</span><div><span className="cp-kicker">{completed ? 'CAMP ARCHIVE' : 'TODAY AT CAMP'}</span><h2>{completed ? 'Your camp memories' : new Intl.DateTimeFormat('en-NG',{dateStyle:'full',timeZone:'Africa/Lagos'}).format(new Date(programme.today+'T12:00:00+01:00'))}</h2><p>{completed ? 'The daily timetable has concluded.' : 'Your approved programme and meals for today.'}</p></div></div>}
 {noPublishedEntries ? upcoming ? <div className="cp-day-pending"><span className="cp-day-pending-icon" aria-hidden="true">☼</span><div><strong>All in one place, when the time comes</strong><p>No action is needed. Your published activities and meals will be shown automatically during camp, using Lagos local time.</p></div><span className="cp-day-pending-status">COMING SOON</span></div> : <div className="cp-day-empty" role="status"><span className="cp-day-empty-symbol" aria-hidden="true">✧</span><div><strong>Today's schedule is not available</strong><p>Activities and meals will appear here automatically when published.</p></div></div> : <div className="cp-day-columns"><article className="cp-card"><h3>{upcoming?'Opening programme':completed?'Final camp programme':"Today’s activities"}</h3>{programme.entries.length?<ol>{(compact?programme.entries.slice(0,2):programme.entries).map(row=><li key={row.id}><time>{row.time_label}</time><strong>{row.title||row.description}</strong>{!compact&&row.title&&<p>{row.description}</p>}{row.certainty !== 'confirmed' && <small>Schedule subject to change</small>}{row.lecturer&&<small>{row.lecturer}</small>}</li>)}</ol>:<p>No activities scheduled for today.</p>}</article>
 <article className="cp-card"><h3>{upcoming?'Arrival meals':completed?'Departure meals':"Today’s meals"}</h3>{food.entries.length?<dl>{food.entries.map(row=><div key={row.id}><dt>{row.meal||row.time_label}</dt><dd>{row.description}</dd></div>)}</dl>:<p>No meals scheduled for today.</p>}</article></div>}</section>
}
