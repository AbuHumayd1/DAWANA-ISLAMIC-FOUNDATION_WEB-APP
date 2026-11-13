import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import postcss from 'postcss'
import fs from 'node:fs'

let server, experience, timetable, home
before(async () => {
  server = await createServer({ configFile:false, server:{middlewareMode:true,hmr:false,ws:false}, appType:'custom' })
  experience = await server.ssrLoadModule('/src/components/dic/CamperExperience.jsx')
  timetable = (await server.ssrLoadModule('/src/components/dic/CamperTimetables.jsx')).default
  home = await server.ssrLoadModule('/src/components/dic/CamperHome.jsx')
})
after(async () => { await server?.close() })
const p = { registration_item_id:1, name:'Example Camper', category:'Example category', eligibility:{eligible:true,code:'verified_paid'},
  issue:null, house_assignment:{name:'Existing House'}, class_assignment:{status:'assigned',name:'Approved class'}, checked_in:false }
const order = { edition:'Camp edition',reference:'PRIVATE-REFERENCE',status:'confirmed',payment_status:'paid',participants:[p] }
const data = { ready:true,total:12,house:'Existing House',standings_ready:true,standings:[{house_id:1,name:'Existing House',rank:1,net:30}],
  history:[],house_leaderboard:[],count:0,page_size:25,page:1 }
const render = (component,props={},route='/dic/participant') => renderToStaticMarkup(createElement(MemoryRouter,{initialEntries:[route]},createElement(component,props)))

test('camper selector is in the compact branded header and remains tied to linked bookings', () => {
  const html = render(experience.default,{orders:[order],expiresAt:'2026-12-23T12:00:00Z'})
  assert.match(html, /<header class="cp-header">.*aria-haspopup="listbox"/s)
  assert.match(html, /My camper/)
  assert.match(html, /Example Camper/)
  const source=fs.readFileSync(new URL('../components/dic/CamperExperience.jsx',import.meta.url),'utf8')
  assert.match(source,/value=\{selected.key\} disabled=\{busy\} onChange=\{onSelect\}/)
  assert.match(source,/value: camperKey\(booking, person\)/)
  assert.doesNotMatch(html, /PARTICIPANTS IN YOUR VERIFIED BOOKING|YOUR LINKED PARTICIPANTS/)
})

test('championship precedes compact personal points and preserves server ranks and scores', () => {
  const html = render(experience.ExperienceContent,{tab:'arena',participant:p,order,data})
  assert.ok(html.indexOf('cw-championship') < html.indexOf('cw-arena-personal'))
  assert.match(html, /aria-label="Position 1"/)
  assert.match(html, /Existing House/)
  assert.match(html, /<b>30<small>points/)
  assert.match(html, /class="cw-own-points">12</)
  assert.doesNotMatch(html, /cp-score-hero/)
})

test('programme keeps publication gates and prioritizes current/upcoming cards without changing data', () => {
  const entries = [1,2,3,4].map(id=>({id,time_label:`${id}:00`,description:`Activity ${id}`}))
  const schedule = {date:'2026-12-23',today:'2026-12-23',state:'published',entries,current:3,upcoming:4}
  const html = render(home.ProgrammePreview,{data:schedule})
  assert.match(html,/Activity 3/); assert.match(html,/Activity 4/)
  assert.doesNotMatch(html,/Activity 1|Activity 2/)
  assert.deepEqual(entries.map(row=>row.id),[1,2,3,4])
  assert.doesNotMatch(render(home.ProgrammePreview,{data:{...schedule,state:'unpublished'}}),/Activity 3/)
})

test('timetable has distinct activity/meal buttons with secondary controls in a closed disclosure', () => {
  const html = render(timetable,{item:1,initialType:'food'})
  assert.match(html, /aria-label="Timetable type"/)
  assert.match(html, /aria-pressed="true"[^>]*>.*Food Timetable/s)
  assert.match(html, /<details class="cw-day-tools"><summary>Programme options/)
  assert.match(html, /Print this day/); assert.match(html,/Refresh/)
  assert.doesNotMatch(html, /<details class="cw-day-tools" open/)
})

test('Me preserves booking, class, ID and secure actions while security/session details start collapsed', () => {
  const html = render(experience.default,{orders:[order],expiresAt:'2026-12-23T12:00:00Z',accountSettings:createElement('p',null,'Existing settings')},'/dic/participant?view=me')
  assert.match(html, /<details class="cw-account-drawer"><summary/)
  for (const text of ['Existing settings','Account Settings','Refresh registrations','Sign out','Session expires']) assert.ok(html.includes(text), text)
  const profile = render(experience.ExperienceContent,{tab:'me',participant:p,order})
  for(const text of ['Example Camper','Approved class','confirmed','paid','Not checked in','PRIVATE-REFERENCE','Awaiting active ID']) assert.ok(profile.includes(text),text)
  assert.doesNotMatch(html, /<details class="cw-account-drawer" open/)
})

test('Explore keeps every care channel and approved activity link in colorful grouped destinations', () => {
  const html = render(experience.ExperienceContent,{tab:'explore',participant:p,order})
  for(const channel of ['daily','welfare','history','final']) assert.ok(html.includes(`/dic/feedback?channel=${channel}`))
  assert.match(html,/href="\/dic#showcase-activities-title"/)
  assert.match(html,/cw-discover-grid/); assert.match(html,/Camp announcements/)
})

test('all new visual rules are portal-scoped and pastel surfaces have readable dark text', () => {
  const css = fs.readFileSync(new URL('../components/dic/CamperWorld.css',import.meta.url),'utf8')
  postcss.parse(css).walkRules(rule=>{ for(const selector of rule.selectors) assert.match(selector,/^\.cp-route(?:\s|$|:)/) })
  assert.doesNotMatch(css,/@font-face|@import|font-family:\s*["']|font-size:\s*(?:3|4)rem/)
  const luminance = hex => hex.match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0)
  for(const background of ['d9eddf','ffe5b7','e5ddf7','d7eaf5','f9d9ce','f7e9ad']) {
    for(const foreground of ['092f23','42564a','526458']) assert.ok((luminance(background)+.05)/(luminance(foreground)+.05)>=4.5)
  }
})
