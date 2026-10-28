import test,{before,after} from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import { selectedCamper } from './camperSelection.js'
let server,Dashboard,select
before(async()=>{server=await createServer({configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});const module=await server.ssrLoadModule('/src/components/dic/CamperDashboard.jsx');Dashboard=module.default;select=selectedCamper})
after(async()=>{await server?.close()})
const orders=[{reference:'BOOKING',edition:'Test camp',status:'confirmed',payment_status:'paid',participants:[
  {registration_item_id:1,name:'Camper One',category:'Camper',participant_number:'DIC-ONE',eligibility:{eligible:true,code:'verified_paid'},issue:{status:'current'},id:'one',house_assignment:{name:'House One',colour:'#147D64'},checked_in:true},
  {registration_item_id:2,name:'Camper Two',category:'Camper',eligibility:{eligible:false,code:'registration_not_verified_paid'},issue:null,id:null,house_assignment:null,checked_in:false}]}]
const render=selection=>renderToStaticMarkup(createElement(MemoryRouter,null,createElement(Dashboard,{orders,selection,busy:false,onSelect(){},onOpenID(){}})))
test('selection projects one camper consistently without retaining previous house or check-in',()=>{
  assert.equal(select(orders,'BOOKING:2').participant.name,'Camper Two')
  const first=render('BOOKING:1'),second=render('BOOKING:2')
  assert.match(first,/House One/);assert.match(first,/>Checked in</)
  assert.match(second,/Not yet assigned/);assert.match(second,/Not checked in/)
  assert.doesNotMatch(second,/House One|DIC-ONE|background-color/)
  assert.match(second,/disabled=""/)
})
test('selection fallback uses current snapshot and never a removed camper',()=>{
  const reduced=[{...orders[0],participants:[orders[0].participants[1]]}]
  assert.equal(select(reduced,'BOOKING:1').participant.name,'Camper Two')
  assert.equal(select([], 'BOOKING:1'),null)
})
test('dashboard retains booking summary and existing links with scoped points loading',()=>{
  const markup=render('BOOKING:1')
  assert.match(markup,/Registration: confirmed/);assert.match(markup,/Payment: paid/)
  assert.match(markup,/href="\/dic#showcase-activities-title"/);assert.match(markup,/href="\/dic\/feedback"/)
  assert.match(markup,/Camp points/)
  assert.doesNotMatch(markup,/welfare|operations\//i)
  const portal=fs.readFileSync(new URL('../pages/ParticipantPortal.jsx',import.meta.url),'utf8')
  assert.match(portal,/href|to="\/dic\/register\/recover"/)
})
