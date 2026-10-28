import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getOperationsData, getReportingExportUrl } from '../services/operationsApi'
import { reportingPath, reportValue, statusOptions } from '../services/reporting'
import './Reporting.css'

export function ReportMetrics({metrics}) {
  return <div className="report-kpis">{metrics.map(item=><article className="ops-panel" key={item.label}><h3>{item.label}</h3><strong>{reportValue(item.value,item.unit)}</strong>{item.description&&<p>{item.description}</p>}</article>)}</div>
}

export function ReportCharts({series}) {
  return <div className="report-charts">{Object.entries(series).map(([title,points])=>{
    const maximum=Math.max(0,...points.map(point=>Math.abs(Number(point.value)||0)))
    return <section className="ops-panel" key={title}><h2>{title}</h2>{!points.length?<p>No matching records.</p>:<dl>{points.map((point,index)=><div key={index}><dt>{point.label}</dt><dd><span className="report-bar" aria-hidden="true" style={{width:maximum?Math.abs(Number(point.value)||0)*100/maximum+'%':'0%'}}/><span>{point.value===null?'Unavailable / privacy threshold':reportValue(point.value)}</span></dd></div>)}</dl>}</section>
  })}</div>
}

export function ReportTable({columns,rows}) {
  if (!rows.length) return <p>No matching detail rows, or detail access is not authorized. Summary data appears above when available.</p>
  return <div className="report-table" tabIndex="0" role="region" aria-label="Report details, scroll horizontally if needed"><table><caption>Filtered report details</caption><thead><tr>{columns.map(key=><th key={key} scope="col">{key.replaceAll('_',' ')}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{columns.map(key=><td key={key}>{reportValue(row[key])}</td>)}</tr>)}</tbody></table></div>
}

export default function Reporting() {
  const [params,setParams]=useSearchParams(),[metadata,setMetadata]=useState({data:null,error:''}),[state,setState]=useState({key:'',data:null,error:''}),[revision,setRevision]=useState(0)
  const domain=params.get('domain')||'overview',edition=params.get('edition')||''
  useEffect(()=>{const controller=new AbortController();getOperationsData('/reporting/?metadata=1',{signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setMetadata({data,error:''})}).catch(error=>{if(!controller.signal.aborted)setMetadata({data:null,error:error.message})});return()=>controller.abort()},[revision])
  let path='',pathError=''
  if (edition) {try {path=reportingPath(params)} catch(error) {pathError=error.message}}
  const requestKey=path+':'+revision
  useEffect(()=>{if(!path)return;const controller=new AbortController();getOperationsData(path,{signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setState({key:requestKey,data,error:''})}).catch(error=>{if(!controller.signal.aborted)setState({key:requestKey,data:null,error:error.message})});return()=>controller.abort()},[path,requestKey])
  const data=state.key===requestKey?state.data:null,error=metadata.error||pathError||(state.key===requestKey?state.error:'')
  const select=(key,value)=>{const query=new URLSearchParams();query.set('edition',key==='edition'?value:edition);query.set('domain',key==='domain'?value:domain);setParams(query)}
  function apply(event){event.preventDefault();const query=new URLSearchParams({edition,domain});for(const [key,value] of new FormData(event.currentTarget)){if(value)query.set(key,value)}setParams(query)}
  function page(number){const query=new URLSearchParams(params);query.set('page',String(number));setParams(query)}
  return <div className="dic-reporting"><div className="ops-page-heading"><div><h1>DIC Reporting and Analytics</h1><p>Recorded evidence, permission-scoped reports and Africa/Lagos dates. Unknown data is never treated as zero.</p></div><button className="ops-button" onClick={()=>setRevision(value=>value+1)}>Refresh</button></div>
    {error&&<p role="alert" className="ops-error">{error}</p>}
    {!metadata.data&&!metadata.error?<p role="status">Loading authorized report choices...</p>:metadata.data&&<>
      <div className="feedback-controls"><label>Camp edition<select value={edition} onChange={event=>select('edition',event.target.value)}><option value="">Choose an edition</option>{metadata.data.editions.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Report<select value={domain} onChange={event=>select('domain',event.target.value)}>{metadata.data.domains.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label></div>
      {!metadata.data.editions.length&&<p>No camp editions are configured.</p>}
      {edition&&<form className="report-filters" key={params.toString()} onSubmit={apply}>
        {['date_from','date_to'].map(key=><label key={key}>{key==='date_from'?'From date':'To date'}<input type="date" name={key} defaultValue={params.get(key)||''}/></label>)}
        {!['feedback','welfare','academic'].includes(domain)&&<label>Registration category<select name="category" defaultValue={params.get('category')||''}><option value="">All categories</option>{data?.categories.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        {statusOptions[domain]&&<label>Status<select name="status" defaultValue={params.get('status')||''}><option value="">All statuses</option>{statusOptions[domain].map(value=><option key={value} value={value}>{value}</option>)}</select></label>}
        {domain==='finance'&&<label>Recorded booking payment status<select name="payment_status" defaultValue={params.get('payment_status')||''}><option value="">All payment states</option>{['not_required','pending','paid','failed','refunded'].map(value=><option key={value} value={value}>{value}</option>)}</select></label>}
        {domain==='feedback'&&<label>Feedback channel<select name="channel" defaultValue={params.get('channel')||''}><option value="">All channels</option>{['daily','final','staff','lecturer'].map(value=><option key={value} value={value}>{value}</option>)}</select></label>}
        {domain==='welfare'&&<><label>Complaint category<select name="concern_category" defaultValue={params.get('concern_category')||''}><option value="">All categories</option>{['health','accommodation','safety','bullying','assistance','other'].map(value=><option key={value} value={value}>{value}</option>)}</select></label><label>Urgency<select name="urgency" defaultValue={params.get('urgency')||''}><option value="">All</option><option value="normal">Normal</option><option value="urgent">Urgent</option></select></label></>}
        {!['welfare','academic'].includes(domain)&&<label>{domain==='attendance'?'Participant UUID':domain==='accommodation'?'House name':domain==='feedback'?'Channel / version / day':'Booking reference'}<input name="q" type="search" maxLength={100} defaultValue={params.get('q')||''}/></label>}
        <label>Sort detail rows<select name="sort" defaultValue={params.get('sort')||'date'}>{[['date','Date ascending'],['-date','Date descending'],['label','Label ascending'],['-label','Label descending'],['value','Value ascending'],['-value','Value descending'],['status','Status']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><button className="ops-button">Apply filters</button><button type="button" className="ops-button" onClick={()=>select('domain',domain)}>Clear filters</button>
      </form>}
    </>}
    {!edition?<p>Choose an edition to load recorded camp data.</p>:!data&&!error?<p role="status">Loading filtered report...</p>:data&&<>
      <h2>{data.title} — {data.edition.name}</h2><p>Generated {data.generated_at} ({data.timezone})</p>
      {!data.available&&<p role="status"><strong>Not Yet Configured</strong></p>}
      <ul className="report-notes">{data.notes.map((note,index)=><li key={index}>{note}</li>)}</ul>
      {data.can_export&&<nav className="feedback-actions" aria-label="Report exports">{['csv','print'].map(format=><a className="ops-button" key={format} target="_blank" rel="noopener noreferrer" href={getReportingExportUrl(params,format)}>{format==='csv'?'Download CSV':'Printable report'}</a>)}</nav>}
      <ReportMetrics metrics={data.metrics}/><ReportCharts series={data.series}/><ReportTable columns={data.columns} rows={data.rows}/>
      {data.count>0&&<nav className="report-pagination" aria-label="Report pages"><button disabled={data.page<=1} onClick={()=>page(data.page-1)}>Previous</button><span>Page {data.page} · {data.count} detail rows</span><button disabled={data.page*data.page_size>=data.count} onClick={()=>page(data.page+1)}>Next</button></nav>}
      <nav className="feedback-actions" aria-label="Authorized drill-downs">{data.drilldowns.filter(item=>item.url.startsWith('/dic/operations/')).map(item=><Link key={item.url} to={item.url}>{item.label}</Link>)}</nav>
    </>}
  </div>
}
