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
 return <section className="cp-day-summary"><div className="cp-day-overview"><span className="cp-day-symbol" aria-hidden="true">▦</span><div><span className="cp-kicker">{upcoming ? 'BEFORE CAMP' : completed ? 'CAMP ARCHIVE' : 'TODAY AT CAMP'}</span><h2>{upcoming ? 'Camp begins soon' : completed ? 'Your camp memories' : new Intl.DateTimeFormat('en-NG',{dateStyle:'full',timeZone:'Africa/Lagos'}).format(new Date(programme.today+'T12:00:00+01:00'))}</h2><p>{upcoming ? 'Your schedule and meals will appear here as they are published.' : completed ? 'Revisit the published programme and camp resources.' : 'Your approved programme and meals for today.'}</p></div></div>
 {noPublishedEntries ? <div className="cp-day-empty" role="status"><span className="cp-day-empty-symbol" aria-hidden="true">✧</span><div><strong>Nothing published yet</strong><p>Activities and meal details will appear here when the camp team releases them.</p></div></div> : <div className="cp-day-columns"><article className="cp-card"><h3>{upcoming?'Opening programme':completed?'Final camp programme':"Today’s activities"}</h3>{programme.entries.length?<ol>{(compact?programme.entries.slice(0,2):programme.entries).map(row=><li key={row.id}><time>{row.time_label}</time><strong>{row.title||row.description}</strong>{!compact&&row.title&&<p>{row.description}</p>}{row.lecturer&&<small>{row.lecturer}</small>}</li>)}</ol>:<p>No programme published yet.</p>}</article>
 <article className="cp-card"><h3>{upcoming?'Arrival meals':completed?'Departure meals':"Today’s meals"}</h3>{food.entries.length?<dl>{food.entries.map(row=><div key={row.id}><dt>{row.meal||row.time_label}</dt><dd>{row.description}</dd></div>)}</dl>:<p>No meals published yet.</p>}</article></div>}</section>
}
