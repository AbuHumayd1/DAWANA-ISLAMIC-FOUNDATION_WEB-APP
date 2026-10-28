import { useEffect,useRef,useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getOperationsData,postOperationsData,getFeedbackExportUrl } from '../services/operationsApi'
import { feedbackChannels,feedbackPath,ratingLabel } from '../services/feedback'
import { ExperienceForm } from '../components/operations/FeedbackForms'
import './Feedback.css'
import { submissionReference } from '../services/houseScoring'

function useFeedbackData(path) {
  const [state,setState]=useState({path:'',data:null,error:''}),[revision,setRevision]=useState(0)
  useEffect(()=>{if(!path)return;let live=true;const controller=new AbortController();getOperationsData(path,{signal:controller.signal}).then(data=>{if(live)setState({path,data,error:''})}).catch(error=>{if(live)setState({path,data:null,error:error.message})});return()=>{live=false;controller.abort()}},[path,revision])
  return {data:state.path===path?state.data:null,error:state.path===path?state.error:'',reload:()=>setRevision(value=>value+1)}
}
function EditionSelect({data,onChange}) {return <label>Camp edition<select value={data.edition?.id||''} onChange={event=>onChange(event.target.value)}>{!data.edition&&<option value="">No edition configured</option>}{data.editions.map(row=><option value={row.id} key={row.id}>{row.name} ({row.year})</option>)}</select></label>}
function ErrorPanel({error,reload}) {return <section className="ops-error" role="alert"><p>{error}</p><button className="ops-button" onClick={reload}>Retry</button></section>}

export function FeedbackSummaryCards({rows,questions}) {
  if(!rows.length)return <section className="ops-panel"><p>No feedback responses for this selection.</p></section>
  return <div className="feedback-summary">{rows.map(row=><article className="ops-panel" key={`${row.channel}-${row.day}-${row.questionnaire_version||1}`}><h2>{feedbackChannels[row.channel]}</h2><p>Camp day: {row.day} / Questionnaire {row.questionnaire_version||1}</p><p>Responses: <strong>{ratingLabel(row.count)}</strong></p>
    {row.suppressed?<p>At least five anonymous responses are needed before displaying this group.</p>:<dl>{Object.entries(row.distributions).map(([key,counts])=><div key={key}><dt>{(row.questions||questions[row.channel]).ratings[key]}</dt><dd>{(row.scale||[[1,'Needs improvement'],[2,'Okay'],[3,'Good']]).map(([rating,label])=>label+': '+(counts[String(rating)]??0)).join(' / ')}</dd></div>)}</dl>}
    {row.recommendation&&<p>Would recommend: Yes {row.recommendation.yes} · No {row.recommendation.no}</p>}
    {row.responses?.map((response,index)=><div className="feedback-details" key={index}>{response.author&&<strong>{response.author}{response.lecturer?` — ${response.lecturer}`:''}</strong>}{Object.entries(response.answers).map(([key,value])=><p key={key}>{(row.questions||questions[row.channel]).comments[key]||key}: {String(value)}</p>)}</div>)}
  </article>)}</div>
}

export default function FeedbackDashboard({user}) {
  const [params,setParams]=useSearchParams(),[details,setDetails]=useState(false)
  const edition=params.get('edition')||'',channel=params.get('channel')||'',day=params.get('day')||''
  let path,errorPath;try{path=feedbackPath('/feedback/',edition,{channel,day,details:details?'1':''})}catch(error){errorPath=error.message}
  const {data,error,reload}=useFeedbackData(path)
  const change=(key,value)=>{const query=new URLSearchParams(params);if(value)query.set(key,value);else query.delete(key);if(key==='edition')query.delete('day');setParams(query)}
  return <><div className="ops-page-heading"><div><h1>Feedback</h1><p>Daily trends, final evaluations and identified staff/lecturer feedback. Confidential welfare reports are excluded.</p></div></div>
    {errorPath||error?<ErrorPanel error={errorPath||error} reload={reload}/>:!data?<p role="status">Loading feedback…</p>:<>
      <div className="feedback-controls"><EditionSelect data={data} onChange={value=>change('edition',value)}/><label>Channel<select value={channel} onChange={event=>change('channel',event.target.value)}><option value="">All general feedback</option>{Object.entries(feedbackChannels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label>Camp day<input type="date" value={day} onChange={event=>change('day',event.target.value)}/></label><button className="ops-button ops-button-secondary" onClick={reload}>Refresh</button>
      </div><p className="ops-small-note">{data.privacy} Questions with fewer than five applicable camper answers are omitted from distributions.</p>
      {user.permissions.feedback_details&&<label><input type="checkbox" checked={details} onChange={event=>setDetails(event.target.checked)}/> Read authorised comments and identified responses (access logged)</label>}
      {data.edition&&user.permissions.export_reports&&<div className="feedback-actions">{['csv','print'].map(format=><a className="ops-button ops-button-secondary" key={format} target="_blank" rel="noopener noreferrer" href={getFeedbackExportUrl(data.edition.id,{channel,day},format)}>{format==='csv'?'Download summary CSV':'Print summary'}</a>)}</div>}
      <FeedbackSummaryCards rows={data.rows} questions={data.questions}/>
    </>}
  </>
}

export function FeedbackEntry({user}) {
  const {data,error,reload}=useFeedbackData('/feedback/options/'),[editionId,setEditionId]=useState(''),[kind,setKind]=useState('')
  const channels=[...(user.permissions.staff_feedback?['staff']:[]),...(user.permissions.lecturer_feedback?['lecturer']:[])]
  const channel=channels.includes(kind)?kind:channels[0],edition=data?.editions.find(row=>String(row.id)===editionId)
  return <><div className="ops-page-heading"><div><h1>Submit feedback</h1><p>Staff and lecturer feedback is identified. Please speak to camp officials in person for welfare concerns.</p></div></div>
    {error?<ErrorPanel error={error} reload={reload}/>:!data?<p role="status">Loading forms…</p>:<>
      <div className="feedback-controls"><label>Camp edition<select value={editionId} onChange={event=>setEditionId(event.target.value)}><option value="">Choose an edition</option>{data.editions.map(row=><option key={row.id} value={row.id}>{row.name} ({row.year})</option>)}</select></label><label>Channel<select value={channel||''} onChange={event=>setKind(event.target.value)}>{channels.map(value=><option key={value} value={value}>{feedbackChannels[value]||'Confidential welfare report'}</option>)}</select></label></div>
      {edition&&channel&&<ExperienceForm key={`${channel}-${editionId}`} channel={channel} spec={data.questions[channel]} ratings={data.ratings} start={edition.camp_start_date} end={edition.camp_end_date} onSave={payload=>postOperationsData(feedbackPath('/feedback/submit/',editionId),payload)}/>}
    </>}
  </>
}

export function WelfareDashboard({user}) {
  const [params,setParams]=useSearchParams(),[reportId,setReportId]=useState('')
  const edition=params.get('edition')||'',status=params.get('status')||'',category=params.get('category')||'',urgency=params.get('urgency')||''
  const {data,error,reload}=useFeedbackData(feedbackPath('/welfare/',edition,{status,category,urgency}))
  const change=(key,value)=>{const query=new URLSearchParams(params);if(value)query.set(key,value);else query.delete(key);setParams(query);setReportId('')}
  return <><h1>Confidential welfare complaints</h1><p>Use only for authorized case management. Internal notes are never shown to campers.</p>{error?<ErrorPanel error={error} reload={reload}/>:!data?<p role="status">Loading complaints...</p>:<>
    <div className="feedback-controls"><EditionSelect data={data} onChange={value=>change('edition',value)}/>{[['status',data.statuses,status],['category',data.categories,category],['urgency',{normal:'Normal',urgent:'Urgent'},urgency]].map(([key,choices,value])=><label key={key}>{key}<select value={value} onChange={event=>change(key,event.target.value)}><option value="">All</option>{Object.entries(choices).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>)}<button onClick={reload}>Refresh</button></div>
    {!data.results.length&&<p>No complaints for this selection.</p>}{data.results.map(row=><div className="welfare-item" key={row.id}><span>{row.category} / {row.urgency} / {data.statuses[row.status]} / {row.time}</span><button onClick={()=>setReportId(row.id)}>Review complaint</button></div>)}
    {reportId&&<WelfareCase key={edition+'-'+reportId} edition={edition} id={reportId} user={user} officers={data.officers} statuses={data.statuses} onSaved={reload}/>}</>}</>
}

function WelfareCase({edition,id,user,officers,statuses,onSaved}) {
  const {data,error,reload}=useFeedbackData(feedbackPath('/welfare/'+id+'/',edition)),[message,setMessage]=useState(''),[busy,setBusy]=useState(false)
  const pending=useRef(false),reference=useRef(null)
  async function save(event){event.preventDefault();if(pending.current)return;const values=new FormData(event.currentTarget);const payload={status:values.get('status'),assigned_to:values.get('assigned_to')?Number(values.get('assigned_to')):null,note:values.get('note'),version:data.version};pending.current=true;setBusy(true);setMessage('');try{reference.current=submissionReference(reference.current,payload);await postOperationsData(feedbackPath('/welfare/'+id+'/',edition),{...payload,request_id:reference.current.id});reference.current=null;setMessage('Case updated.');reload();onSaved()}catch(error){setMessage(error.message)}finally{pending.current=false;setBusy(false)}}
  return <section className="ops-panel feedback-form"><h2>Confidential case</h2>{error?<ErrorPanel error={error} reload={reload}/>:!data?<p role="status">Loading case...</p>:<><p>Affected camper: {data.affected_camper||'Not recorded (legacy/staff report)'}</p><p>Reporter: {data.reporter}</p><p>{data.urgency} / Preferred contact: {data.preferred_contact}</p><p className="welfare-private">{data.description}</p><p>Status: {statuses[data.status]}</p>
    {user.permissions.manage_welfare&&<form onSubmit={save}><fieldset disabled={busy}><label>Status<select name="status" defaultValue={data.status}>{Object.entries(statuses).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label><label>Assigned officer<select name="assigned_to" defaultValue={data.assigned_to||''}><option value="">Unassigned</option>{officers.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Confidential internal note<textarea name="note" required maxLength={3000}/></label><button>Save case update</button></fieldset></form>}
    <h3>Private case history</h3>{data.events.map((row,index)=><p className="welfare-private" key={index}>{row.time} / {row.kind} / {row.staff}: {row.note}</p>)}</>}<p role="status">{message}</p></section>
}
