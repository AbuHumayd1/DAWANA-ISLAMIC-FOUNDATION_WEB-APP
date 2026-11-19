import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getOperationsData, postOperationsData, getAftercampReportUrl } from '../services/operationsApi'
import './AftercampReport.css'

function Metrics({metrics}) {
  return <div className="aftercamp-metrics">{metrics.slice(0,8).map(metric=><div className="aftercamp-metric" key={metric.label}><span>{metric.label}</span><strong>{metric.display}</strong></div>)}</div>
}
function EvidenceChart({chart}) {
  const points = chart.points.filter(point=>point.value!==null)
  if (!points.length) return null
  return <section className="aftercamp-chart"><h4>{chart.title}</h4>
    {points.slice(0,12).map((point,i)=><div className="aftercamp-chart-row" key={i}>
      <span>{point.label}</span><div className="aftercamp-chart-track"><span style={{width:point.width+'%'}}/></div><b>{point.display}</b>
    </div>)}
  </section>
}

function CommitteeEditor({ edition, items, onSaved }) {
  const [topic,setTopic]=useState(items[0]?.topic||'')
  const selected=items.find(item=>item.topic===topic)||items[0]
  const [draft,setDraft]=useState(selected||null)
  const [busy,setBusy]=useState(false)
  const [feedback,setFeedback]=useState('')
  useEffect(()=>{setDraft(selected||null);setFeedback('')},[selected?.topic,selected?.status,selected?.findings,selected?.challenges,selected?.recommendations,selected?.evidence_reference])
  if(!selected||!draft)return null
  async function execute(action) {
    setBusy(true);setFeedback('')
    try{
      await postOperationsData('/aftercamp-report/',{
        edition:Number(edition),topic:selected.topic,action,
        ...(action==='save'?{
          findings:draft.findings,challenges:draft.challenges,
          recommendations:draft.recommendations,evidence_reference:draft.evidence_reference
        }:{})
      })
      setFeedback(action==='save'?'Draft saved. It is not included in the report until approved.':action==='approve'?'Assessment approved for report publication.':'Assessment reopened as draft.')
      onSaved()
    }catch(error){setFeedback(error.message||'Unable to save committee assessment.')}
    finally{setBusy(false)}
  }
  const approved=selected.status==='approved'
  return <section className="aftercamp-section aftercamp-editor">
    <span className="aftercamp-eyebrow">ADMINISTRATOR REVIEW · COMMITTEE EVIDENCE</span>
    <h3>Committee findings and recommendations</h3>
    <p>Draft committee observations are private. Only an explicitly approved assessment enters downloaded reports. Reference minutes, attendance records or an approved committee submission.</p>
    <label>Assessment area<select value={selected.topic} onChange={event=>setTopic(event.target.value)}>
      {items.map(item=><option key={item.topic} value={item.topic}>{item.title} · {item.status}</option>)}
    </select></label>
    <div className="aftercamp-editor-fields">
      {[
        ['findings','Findings and verified outcomes',10000],
        ['challenges','Challenges and lessons learned',6000],
        ['recommendations','Recommendations and next actions',6000],
        ['evidence_reference','Evidence reference or committee minutes',1500]
      ].map(([field,label,max])=><label key={field}>{label}
        <textarea value={draft[field]||''} rows={field==='evidence_reference'?2:4}
          maxLength={max} disabled={approved||busy}
          onChange={event=>setDraft(current=>({...current,[field]:event.target.value}))}/>
      </label>)}
    </div>
    <div className="aftercamp-editor-actions">
      {!approved&&<button type="button" className="ops-button ops-button-secondary" disabled={busy} onClick={()=>execute('save')}>Save private draft</button>}
      {!approved&&<button type="button" className="ops-button ops-button-primary" disabled={busy||!selected.findings||!selected.evidence_reference} onClick={()=>execute('approve')}>Approve saved assessment</button>}
      {approved&&<button type="button" className="ops-button ops-button-secondary" disabled={busy} onClick={()=>execute('reopen')}>Reopen for revision</button>}
      <span role="status">{feedback}</span>
    </div>
    {!approved&&<small>Save your edits before approval. Approval requires saved findings and a traceable evidence reference.</small>}
  </section>
}
export default function AftercampReport() {
  const [params,setParams] = useSearchParams()
  const [metadata,setMetadata] = useState({data:null,error:''})
  const [report,setReport] = useState({data:null,error:'',loading:false})
  const [refresh,setRefresh] = useState(0)
  const edition = params.get('edition') || ''
  useEffect(()=>{
    const controller=new AbortController()
    getOperationsData('/reporting/?metadata=1',{signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setMetadata({data,error:''})})
      .catch(error=>{if(!controller.signal.aborted)setMetadata({data:null,error:error.message})})
    return()=>controller.abort()
  },[refresh])
  useEffect(()=>{
    if(!edition){setReport({data:null,error:'',loading:false});return undefined}
    const controller=new AbortController()
    setReport({data:null,error:'',loading:true})
    getOperationsData('/aftercamp-report/?edition='+encodeURIComponent(edition),{signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setReport({data,error:'',loading:false})})
      .catch(error=>{if(!controller.signal.aborted)setReport({data:null,error:error.message,loading:false})})
    return()=>controller.abort()
  },[edition,refresh])
  const data=report.data
  return <main className="aftercamp-page">
    <div className="ops-page-heading aftercamp-header">
      <div><span className="aftercamp-eyebrow">EDITION PERFORMANCE · EVIDENCE BRIEF</span><h1>Comprehensive camp report</h1><p>A consolidated view of available camp records. No repeated filters or technical spreadsheets.</p></div>
      <button type="button" className="ops-button ops-button-secondary" onClick={()=>setRefresh(n=>n+1)}>↻ Refresh report</button>
    </div>
    <div className="aftercamp-controls">
      <label>Camp edition<select value={edition} onChange={e=>setParams({edition:e.target.value})}><option value="">Choose an edition</option>{metadata.data?.editions?.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      {data&&<div className="aftercamp-export-actions">
        <a className="ops-button ops-button-primary" href={getAftercampReportUrl(edition,'docx')}>Download consolidated Word report</a>
        <a className="ops-button ops-button-secondary" href={getAftercampReportUrl(edition,'print')} target="_blank" rel="noopener noreferrer">Print or save as PDF</a>
        <Link className="ops-button ops-button-secondary" to={'/dic/operations/reporting?edition='+encodeURIComponent(edition)+'&domain=registration'}>Detailed operational analytics</Link>
      </div>}
    </div>
    {(metadata.error||report.error)&&<p role="alert" className="ops-error">{metadata.error||report.error}</p>}
    {report.loading&&<p role="status">Compiling authorized camp measurements…</p>}
    {!edition&&!metadata.error&&<p className="aftercamp-empty">Choose an edition to see its consolidated evidence brief.</p>}
    {data&&<>
      <section className="aftercamp-overview">
        <span className="aftercamp-eyebrow">{data.report_status}</span>
        <h2>{data.edition.name}</h2>
        <p>Measured at {new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short',timeZone:'Africa/Lagos'}).format(new Date(data.generated_at))} WAT. This report does not invent unrecorded outcomes.</p>
        <div className="aftercamp-coverage"><strong>{data.covered_count} / {data.total_sections}</strong><span>Reporting domains with recorded measures available to your account</span></div>
      </section>
      <section className="aftercamp-section aftercamp-executive">
        <span className="aftercamp-eyebrow">EXECUTIVE OVERVIEW</span>
        <h3>What the recorded evidence tells us</h3>
        <div className="aftercamp-highlights">{data.executive_highlights?.map(item=><article key={item.title}>
          <h4>{item.title}</h4><p>{item.finding}</p>
        </article>)}</div>
        {data.evidence_gaps?.length>0&&<details className="aftercamp-notes"><summary>Evidence requiring follow-up ({data.evidence_gaps.length})</summary>
          <ul>{data.evidence_gaps.map(item=><li key={item.title}><strong>{item.title}:</strong> {item.reason}</li>)}</ul></details>}
        <p className="aftercamp-review-status">{data.committee_approval_complete?'All committee assessment topics have been approved.':'Committee approval: '+data.assessment_coverage+' of '+data.committee_approvals_required+' assessment topics approved. Unapproved material is excluded from downloads.'}</p>
      </section>
      <div className="aftercamp-section-list">{data.sections.map(section=><section key={section.domain} className="aftercamp-section">
        <div className="aftercamp-section-heading"><div><span className="aftercamp-eyebrow">{section.state==='recorded'?'REPORTED EVIDENCE':section.state==='restricted'?'ACCESS RESTRICTED':'DATA UNAVAILABLE'}</span><h3>{section.title}</h3></div></div>
        <p className="aftercamp-section-summary">{section.summary}</p>
        {section.state==='recorded'&&<><Metrics metrics={section.metrics}/><div className="aftercamp-chart-grid">{section.charts.slice(0,3).map(chart=><EvidenceChart key={chart.title} chart={chart}/>)}</div></>}
        {section.notes.length>0&&<details className="aftercamp-notes"><summary>Data definitions and limitations</summary><ul>{section.notes.map((note,i)=><li key={i}>{note}</li>)}</ul></details>}
      </section>)}</div>
      <section className="aftercamp-section aftercamp-editorial-summary">
        <span className="aftercamp-eyebrow">APPROVED COMMITTEE REVIEW</span>
        <h3>Camp achievements, challenges and recommendations</h3>
        {data.committee_assessments?.length ? data.committee_assessments.map(assessment=>
          <article key={assessment.topic} className="aftercamp-assessment">
            <h4>{assessment.title}</h4>
            {assessment.findings&&<p><strong>Findings:</strong> {assessment.findings}</p>}
            {assessment.challenges&&<p><strong>Challenges:</strong> {assessment.challenges}</p>}
            {assessment.recommendations&&<p><strong>Recommendations:</strong> {assessment.recommendations}</p>}
          </article>) : <p>No approved committee assessment has been recorded for this edition.</p>}
      </section>
      {data.editorial_drafts?.length>0&&<CommitteeEditor edition={edition} items={data.editorial_drafts} onSaved={()=>setRefresh(n=>n+1)}/>}
      <details className="aftercamp-notes aftercamp-general-notes"><summary>Scope, methodology and missing sources</summary><ul>{data.methodology.map((note,i)=><li key={i}>{note}</li>)}</ul></details>
    </>}
  </main>
}
