import test,{before,after} from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { feedbackPath,ratingLabel } from './feedback.js'
import { visibleOperationsNavigation } from './operationsNavigation.js'
import { getFeedbackExportUrl } from './operationsApi.js'
import fs from 'node:fs'

let server,Cards,Experience,Welfare
before(async()=>{server=await createServer({configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});Cards=(await server.ssrLoadModule('/src/pages/Feedback.jsx')).FeedbackSummaryCards;const forms=await server.ssrLoadModule('/src/components/operations/FeedbackForms.jsx');Experience=forms.ExperienceForm;Welfare=forms.WelfareForm})
after(async()=>{await server?.close()})
const render=(component,props)=>renderToStaticMarkup(createElement(component,props))

test('welfare UI uses authenticated APIs and explicit camper selection',()=>{
  const camper=fs.readFileSync(new URL('../pages/CamperFeedback.jsx',import.meta.url),'utf8')
  assert.match(camper,/WelfareForm/);assert.match(camper,/item_id:item.id/);assert.match(camper,/ComplaintHistory/)
  const ops=fs.readFileSync(new URL('../pages/Feedback.jsx',import.meta.url),'utf8')
  assert.match(ops,/manage_welfare/);assert.match(ops,/Confidential internal note/)
  const links=visibleOperationsNavigation({can_access_campsite:true,permissions:{welfare:true}})
  assert.ok(links.some(row=>row.to.endsWith('/welfare')))
})

test('feedback filters and exports validate edition and do not grant welfare navigation',()=>{
  assert.equal(feedbackPath('/feedback/','1',{channel:'daily',day:'2026-12-23'}),'/feedback/?edition=1&channel=daily&day=2026-12-23')
  assert.throws(()=>feedbackPath('/feedback/','../'))
  assert.match(getFeedbackExportUrl('1',{channel:'staff'},'csv'),/edition=1&channel=staff&export=csv/)
  assert.throws(()=>getFeedbackExportUrl('1',{},'private-welfare'))
  const links=visibleOperationsNavigation({can_access_campsite:true,permissions:{feedback:true}})
  assert.ok(links.some(row=>row.to.endsWith('/feedback')))
  assert.ok(!links.some(row=>row.to.endsWith('/welfare')||row.to.endsWith('/feedback-submit')))
})
test('empty and suppressed summaries do not invent zeros or expose comments',()=>{
  assert.equal(ratingLabel(null),'Below privacy threshold')
  assert.equal(ratingLabel(0),'0')
  assert.match(render(Cards,{rows:[],questions:{}}),/No feedback responses/)
  const markup=render(Cards,{rows:[{channel:'daily',day:'2026-12-23',count:null,suppressed:true,distributions:{}}],questions:{}})
  assert.match(markup,/Below privacy threshold/)
  assert.doesNotMatch(markup,/Responses: <strong>0|<textarea/)
})
test('daily summary renders distributions, recommendation totals and escaped authorised comments',()=>{
  const markup=render(Cards,{rows:[{channel:'final',day:'2027-01-01',count:5,suppressed:false,distributions:{overall:{'1':0,'2':2,'3':3}},recommendation:{yes:4,no:1},responses:[{ratings:{},answers:{suggestions:'<script>private</script>'}}]}],questions:{final:{ratings:{overall:'Camp overall'},comments:{suggestions:'Suggestions'}}}})
  assert.match(markup,/Okay: 2/);assert.match(markup,/Yes 4/);assert.match(markup,/&lt;script&gt;/);assert.doesNotMatch(markup,/<script>/)
})
test('experience forms have labelled mobile controls and no identity inputs',()=>{
  const markup=render(Experience,{channel:'daily',spec:{ratings:{learning:'Learning today'},comments:{suggestions:'Suggestions'}},ratings:[[1,'Needs improvement'],[2,'Okay'],[3,'Good']],start:'2026-12-23',end:'2027-01-01',onSave(){}})
  assert.match(markup,/name="day"/);assert.match(markup,/name="rating-learning"/);assert.match(markup,/name="answer-suggestions"/)
  assert.doesNotMatch(markup,/name="(?:participant|email|phone|house|author)/)
})
test('welfare is explicitly identified, confidential and not emergency dispatch',()=>{
  const markup=render(Welfare,{categories:{health:'Health concern'},urgent:'Contact a welfare officer immediately. Not instant emergency assistance.',reporterNotice:'Identified through your verified booking.',onSave(){}})
  assert.match(markup,/Identified through/);assert.match(markup,/Not instant emergency assistance/);assert.match(markup,/name="assistance_person"/);assert.match(markup,/name="description"/)
})

test('five point reports preserve labels and tutor questions omit accommodation',()=>{
  const scale=[[1,'Very Poor'],[2,'Poor'],[3,'Fair'],[4,'Very Good'],[5,'Excellent']]
  const markup=render(Cards,{rows:[{channel:'daily',day:'2026-12-25',questionnaire_version:2,count:5,suppressed:false,scale,distributions:{learning:{1:0,2:1,3:1,4:1,5:2}},questions:{ratings:{learning:'Classes'},comments:{}}}],questions:{}})
  assert.match(markup,/Excellent: 2/);assert.match(markup,/Very Poor: 0/);assert.doesNotMatch(markup,/Needs improvement/)
  const form=render(Experience,{channel:'daily',spec:{ratings:{learning:'Classes'},comments:{}},ratings:scale,today:'2026-12-25',start:'2026-12-23',end:'2027-01-01',onSave(){}})
  assert.match(form,/value="2026-12-25"/);assert.match(form,/readOnly=""/);assert.doesNotMatch(form,/rating-comfort/)
})
