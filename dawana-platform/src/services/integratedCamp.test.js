import test,{before,after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {MemoryRouter} from 'react-router-dom'
import {portalView,activeDestination} from './premiumPortal.js'
let server,Experience
before(async()=>{server=await createServer({configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});Experience=(await server.ssrLoadModule('/src/components/dic/CamperExperience.jsx')).default})
after(async()=>await server?.close())
const person={id:'person-1',name:'Authorized Camper',registration_item_id:1,eligibility:{eligible:true,code:'verified_paid'},registration_basis:'tutor'}
const order={reference:'booking',edition:'DIC 2026',participants:[person]}
const render=orders=>renderToStaticMarkup(createElement(MemoryRouter,null,createElement(Experience,{orders,expiresAt:'2026-12-23T10:00:00Z'})))
test('one camper is named without an interactive listbox',()=>{const html=render([order]);assert.match(html,/cp-single-camper/);assert.match(html,/Authorized Camper/);assert.doesNotMatch(html,/aria-haspopup="listbox"/)})
test('multiple authorized campers retain a functioning controlled selector',()=>{const html=render([{...order,participants:[person,{...person,id:'person-2',registration_item_id:2,name:'Authorized Sibling'}]}]);assert.match(html,/aria-haspopup="listbox"/);assert.match(html,/My camper/)})
test('recordings and certificates resolve within the existing Me navigation',()=>{for(const view of ['recordings','certificate']){assert.equal(portalView(view),view);assert.equal(activeDestination(view),'me')}})
