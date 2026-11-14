import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
let server, Table
before(async()=>{
 server=await createServer({configFile:false,plugins:[{name:'test-registration-table',transform(code,id){if(id.replaceAll('\\','/').endsWith('/src/pages/Operations.jsx'))return `${code}\nexport { RegistrationTable as TestRegistrationTable }\n`}}],server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'})
 Table=(await server.ssrLoadModule('/src/pages/Operations.jsx')).TestRegistrationTable
})
after(async()=>{await server?.close()})
const base={id:'11111111-1111-4111-8111-111111111111',created_at:'2026-11-14',participant_count:1,categories:['Adult'],payment_status:'failed',quoted_total_ngn:'40000',deletion:{eligible:true,reason:''},test_cleanup:{can_archive:true,archive_reason:''},restore:{eligible:false}}
const render=row=>renderToStaticMarkup(createElement(MemoryRouter,null,createElement(Table,{rows:[row],count:1})))
const button=(html,label)=>html.match(new RegExp(`<button[^>]*>${label}</button>`))?.[0]
test('each eligible failed-payment registration row has separate enabled Delete and Archive controls',()=>{
 const html=render(base)
 assert.match(html, /Actions<\/th>/)
 for(const label of ['Delete','Archive']){assert.ok(button(html,label));assert.doesNotMatch(button(html,label),/disabled/)}
 assert.equal(button(html,'Restore'),undefined)
})
test('paid or unresolved rows keep visible disabled actions and a clear reason',()=>{
 const html=render({...base,payment_status:'paid',deletion:{eligible:false,reason:'Verified payment is protected.'},test_cleanup:{can_archive:false,archive_reason:'Paid records are protected.'}})
 for(const label of ['Delete','Archive'])assert.match(button(html,label),/disabled/)
 assert.ok(html.includes('Verified payment is protected.'))
})
test('Trash rows expose Restore while distinguishing deleted status from Archive',()=>{
 const html=render({...base,record_state:'deleted',deletion:{eligible:false,reason:'Already in Trash.'},test_cleanup:{can_archive:false,archive_reason:'Restore first.'},restore:{eligible:true,reason:''}})
 assert.ok(html.includes('Deleted / Trash'))
 assert.doesNotMatch(button(html,'Restore'),/disabled/)
 for(const label of ['Delete','Archive'])assert.match(button(html,label),/disabled/)
})
