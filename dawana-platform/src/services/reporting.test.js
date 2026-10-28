import test,{before,after} from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { reportingPath, reportValue, statusOptions } from './reporting.js'
import { getReportingExportUrl } from './operationsApi.js'
import { visibleOperationsNavigation } from './operationsNavigation.js'

let server,components
before(async()=>{server=await createServer({configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});components=await server.ssrLoadModule('/src/pages/Reporting.jsx')})
after(async()=>{await server?.close()})
const render=(name,props)=>renderToStaticMarkup(createElement(MemoryRouter,null,createElement(components[name],props)))

test('report requests require an edition and preserve only supported filters',()=>{
  assert.throws(()=>reportingPath({domain:'registration'}))
  assert.throws(()=>reportingPath({edition:'../',domain:'registration'}))
  assert.throws(()=>reportingPath({edition:'1',domain:'passwords'}))
  const path=reportingPath({edition:'1',domain:'attendance',date_from:'2026-12-25',category:'2',q:'reference',page:'3',sort:'-date',token:'SECRET'})
  assert.match(path,/edition=1&domain=attendance/);assert.match(path,/date_from=2026-12-25/)
  assert.match(path,/page=3/);assert.doesNotMatch(path,/SECRET|token/)
})

test('screen, CSV and print share filters; export excludes page and cannot choose private formats',()=>{
  const params=new URLSearchParams({edition:'1',domain:'feedback',channel:'daily',date_from:'2026-12-25',page:'2'})
  for(const format of ['csv','print']){
    const url=getReportingExportUrl(params,format)
    assert.match(url,/domain=feedback/);assert.match(url,/channel=daily/);assert.match(url,/date_from=2026-12-25/)
    assert.ok(url.endsWith('export='+format));assert.doesNotMatch(url,/page=/)
  }
  assert.throws(()=>reportingPath(params,'private-welfare'))
})

test('unknown values are not zero; cash uses kobo and recommendation counts remain numbers',()=>{
  assert.equal(reportValue(null),'Unavailable');assert.equal(reportValue(undefined),'Unavailable')
  assert.equal(reportValue(0),'0');assert.match(reportValue(12345,'NGN kobo'),/123\.45/)
  assert.equal(reportValue(25,'percent'),'25%');assert.equal(reportValue(false),'No')
})

test('KPI and chart output preserve empty data and anonymous suppression',()=>{
  const metrics=render('ReportMetrics',{metrics:[{label:'Confirmed absent',value:null,description:'A missing scan is not absence.'}]})
  assert.match(metrics,/Unavailable/);assert.doesNotMatch(metrics,/>0</)
  const charts=render('ReportCharts',{series:{Feedback:[{label:'Daily v2',value:null}],Arrivals:[]}})
  assert.match(charts,/privacy threshold/);assert.match(charts,/No matching records/)
})

test('tables escape content and distinguish missing detail permission from fabricated rows',()=>{
  assert.match(render('ReportTable',{columns:[],rows:[]}),/No matching detail rows/)
  const markup=render('ReportTable',{columns:['label','value'],rows:[{label:'<script>private</script>',value:0}]})
  assert.match(markup,/&lt;script&gt;/);assert.doesNotMatch(markup,/<script>/)
  assert.match(markup,/scope="col"/);assert.match(markup,/role="region"/)
})

test('report navigation requires existing report permission and no longer advertises a planned page',()=>{
  assert.ok(!visibleOperationsNavigation({can_access_campsite:true,permissions:{}}).some(row=>row.to.endsWith('/reporting-hub')))
  const link=visibleOperationsNavigation({can_access_campsite:true,permissions:{export_reports:true}}).find(row=>row.to.endsWith('/reporting-hub'))
  assert.ok(link);assert.equal(link.planned,undefined)
  assert.ok(!statusOptions.finance.includes('paid'));assert.ok(statusOptions.finance.includes('successful'))
})

test('report initial state loads choices without invented production totals',()=>{
  const markup=render('default',{})
  assert.match(markup,/Reporting and Analytics/);assert.match(markup,/Loading authorized report choices/)
  assert.match(markup,/Choose an edition/);assert.doesNotMatch(markup,/Confirmed bookings: 0|Gross verified collections: 0/)
})
