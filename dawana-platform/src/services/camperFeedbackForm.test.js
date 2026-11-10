import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import postcss from 'postcss'
import { confirmedFeedbackResult, experiencePayload, validateExperience } from './camperFeedbackForm.js'

let server, Form, Rating, ClassCard, Header
before(async()=>{
  server=await createServer({configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'})
  const module=await server.ssrLoadModule('/src/components/dic/CamperExperienceForm.jsx')
  Form=module.default;Rating=module.ExperienceRating
  ClassCard=(await server.ssrLoadModule('/src/components/dic/PortalPhase3.jsx')).ClassAssignmentCard
  Header=(await server.ssrLoadModule('/src/components/dic/CamperFeedbackLayout.jsx')).FeedbackChannelNav
})
after(async()=>{await server?.close()})
const render=(component,props)=>renderToStaticMarkup(createElement(component,props))
const spec={ratings:{learning:"Today's classes and learning activities",meals:"Today's meals",comfort:'Accommodation and comfort',organisation:"Today's activities and general organization"},optional_ratings:['comfort'],comments:{suggestions:'Comments and suggestions (optional)'}}
const ratings=[[1,'Very Poor'],[2,'Poor'],[3,'Fair'],[4,'Very Good'],[5,'Excellent']]
const state={spec,ratings,choices:{learning:'5',meals:'3',organisation:'4'},comments:{suggestions:'Non-identifying feedback'},recommend:'',channel:'daily',day:'2026-12-23'}

test('real payload keeps exact server fields, scale values, date and optional accommodation semantics',()=>{
  assert.deepEqual(experiencePayload(state),{channel:'daily',day:'2026-12-23',ratings:{learning:5,meals:3,organisation:4},answers:{suggestions:'Non-identifying feedback'}})
  assert.deepEqual(validateExperience(state),{})
  const notApplicable={...state,choices:{...state.choices,comfort:'not_applicable'}}
  assert.equal('comfort' in experiencePayload(notApplicable).ratings,false)
  const extra={...state,choices:{...state.choices,overall:'5',welfare:'5'},comments:{...state.comments,identity:'not forwarded'}}
  assert.equal('overall' in experiencePayload(extra).ratings,false)
  assert.equal('identity' in experiencePayload(extra).answers,false)
})

test('missing or unsupported ratings and oversized comments cannot become an API payload',()=>{
  for(const choices of [{...state.choices,meals:''},{...state.choices,learning:'excellent'},{...state.choices,organisation:'6'}]) {
    assert.ok(Object.keys(validateExperience({...state,choices})).length)
    assert.throws(()=>experiencePayload({...state,choices}))
  }
  assert.throws(()=>experiencePayload({...state,comments:{suggestions:'x'.repeat(1001)}}))
})

test('final recommendation is required and no recommendation is added to daily feedback',()=>{
  assert.ok(validateExperience({...state,channel:'final'}).recommend)
  assert.equal(experiencePayload({...state,channel:'final',recommend:'no'}).recommend,false)
  assert.equal('recommend' in experiencePayload({...state,recommend:'yes'}),false)
})

test('success is restricted to an explicitly accepted result and duplicates have their own state',()=>{
  assert.equal(confirmedFeedbackResult({accepted:true,duplicate:false}),'success')
  assert.equal(confirmedFeedbackResult({accepted:true,duplicate:true}),'duplicate')
  for(const result of [undefined,null,{}, {accepted:false}, {duplicate:true}])assert.throws(()=>confirmedFeedbackResult(result))
})

test('descriptive rating radios expose the question, text labels, checked state and accessible error',()=>{
  const html=render(Rating,{id:'learning',title:'Classes and learning',options:[[5,'Excellent'],[4,'Very Good'],[3,'Good'],[2,'Fair'],[1,'Poor']],value:'4',onChange(){},error:'Choose a rating.'})
  assert.match(html,/<legend>Classes and learning/)
  assert.equal((html.match(/type="radio"/g)||[]).length,5)
  assert.match(html,/class="cf-rating-choice cf-rating-tone-1 is-selected"/)
  assert.match(html,/checked="" value="4"|value="4" checked=""/)
  assert.match(html,/aria-describedby="learning-error"/)
  for(const text of ['Excellent','Very Good','Good','Fair','Poor'])assert.ok(html.includes(text))
})

test('real form renders server question labels and current scale without silently introducing Good or extra categories',()=>{
  const html=render(Form,{channel:'daily',spec,ratings,start:'2026-12-23',end:'2027-01-01',today:'2026-12-23'})
  assert.match(html,/Very Poor/);assert.doesNotMatch(html,/>Good</)
  assert.doesNotMatch(html,/Your overall daily experience|Welfare and camp organisation/)
  assert.match(html,/maxLength="1000"/);assert.match(html,/Send feedback/)
  assert.match(html,/Not applicable/)
})

test('demo branch stops before payload creation or real save and form never persists answers',()=>{
  const source=fs.readFileSync(new URL('../components/dic/CamperExperienceForm.jsx',import.meta.url),'utf8')
  const demoBranch=source.slice(source.indexOf('if (demo) {'),source.indexOf('pending.current = true;'))
  assert.match(demoBranch,/setStatus\('demo_complete'\)/)
  assert.match(demoBranch,/return/)
  assert.doesNotMatch(demoBranch,/await onSave|experiencePayload\(/)
  assert.doesNotMatch(source,/localStorage|sessionStorage|fetch\(|sendBeacon|console\./)
  assert.match(source,/event.preventDefault\(\)/)
})

test('My Class shows only a truly assigned name, keeps house separate and excludes fixture prose',()=>{
  const assigned=render(ClassCard,{participant:{class_assignment:{status:'assigned',name:'Approved learning circle',message:'Illustrative class assignment only'},house_assignment:{name:'Different house'}}})
  assert.match(assigned,/My Class/);assert.match(assigned,/Approved learning circle/)
  assert.doesNotMatch(assigned,/Illustrative|Different house|Your teaching class/)
  const pending=render(ClassCard,{participant:{class_assignment:{name:'Not approved'},house_assignment:{name:'Different house'}}})
  assert.match(pending,/Not yet assigned/);assert.match(pending,/Your class will appear here/)
  assert.doesNotMatch(pending,/Not approved|Different house/)
})

test('feedback navigation retains daily, complaint submission, status and final evaluation',()=>{
  const html=renderToStaticMarkup(createElement(MemoryRouter,null,createElement(Header,{channel:'daily'})))
  for(const channel of ['daily','welfare','history','final'])assert.ok(html.includes(`/dic/feedback?channel=${channel}`))
  assert.equal((html.match(/aria-current="page"/g)||[]).length,1)
})

test('feedback styling uses component scope, responsive rating grids and readable surface contrast',()=>{
  const css=fs.readFileSync(new URL('../components/dic/CamperFeedbackWorld.css',import.meta.url),'utf8')
  postcss.parse(css).walkRules(rule=>{for(const selector of rule.selectors)assert.match(selector,/^\.(?:cw-feedback-page|cw-experience-form|cf-[\w-]+)/)})
  assert.doesNotMatch(css,/@import|@font-face|:root\s*\{/)
  assert.match(css,/grid-template-columns:repeat\(5,minmax\(0,1fr\)\)/)
  assert.match(css,/@media \(max-width:699px\)/)
  assert.match(css,/grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/)
  assert.match(css,/\.cf-rating-choice:focus-within/)
  const luminance=hex=>hex.match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0)
  for(const bg of ['e6efdf','f5e8d2','e9e2f3','f5edce'])for(const fg of ['092f23','526458'])assert.ok((luminance(bg)+.05)/(luminance(fg)+.05)>=4.5)
})
