import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

let server, Select, ID, Earn
before(async()=>{
  server=await createServer({configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'})
  Select=(await server.ssrLoadModule('/src/components/dic/CamperSelect.jsx')).default
  ID=(await server.ssrLoadModule('/src/components/dic/DigitalIDPresentation.jsx')).default
  Earn=(await server.ssrLoadModule('/src/components/dic/EarnPoints.jsx')).default
})
after(async()=>{await server?.close()})
const render=(Component,props)=>renderToStaticMarkup(createElement(Component,props))
test('camper selector exposes labelled controlled state, escapes text and disables empty choices',()=>{
  const html=render(Select,{label:'My camper',value:'a',options:[{value:'a',label:'<Camper>'}],onChange(){}})
  assert.match(html,/aria-haspopup="listbox"/);assert.match(html,/aria-expanded="false"/)
  assert.match(html,/aria-labelledby=/);assert.match(html,/&lt;Camper&gt;/)
  assert.match(render(Select,{label:'Camper',value:'',options:[],onChange(){}}),/disabled=""/)
})
test('ID layout uses existing authorized format routes without exposing QR secrets',()=>{
  const id='12345678-1234-4234-8234-123456789abc'
  const html=render(ID,{card:{id,name:'Synthetic camper',participant_number:'TEST'},onClose(){}})
  for(const format of ['pvc','a6','portrait'])assert.ok(html.includes(`format=${format}`))
  assert.equal((html.match(/download=1/g)||[]).length,3)
  assert.match(html, new RegExp(`<a[^>]*href="/api/v1/dic/participant/enrollments/${id}/card/\\?format=pvc"[^>]*>Preview PVC Card</a>`))
  const staff = render(ID, { card: { id, name: 'Synthetic camper', participant_number: 'TEST' }, staff: true, onClose() {} })
  assert.match(staff, new RegExp(`<a[^>]*href="/api/v1/dic/ids/cards/${id}/\\?format=pvc"[^>]*>Preview PVC Card</a>`))
  assert.doesNotMatch(html, /\/dic\/ids\/cards\//)
  assert.doesNotMatch(staff, /\/dic\/participant\/enrollments\//)
  assert.doesNotMatch(html,/<iframe|<object|<embed/)
  assert.match(html,/Open &amp; print/)
  assert.doesNotMatch(html,/verification_secret|verification_digest|token=|data:image/)
  const security=fs.readFileSync(new URL('../../../backend/dic/identity_views.py',import.meta.url),'utf8')
  assert.match(security,/X-Frame-Options'\] = 'DENY'/)
  assert.match(security,/frame-ancestors 'none'/)
})
test('Earn Points displays only supplied policy and never invents submission or completion states',()=>{
  assert.match(render(Earn,{catalogue:{ready:false,activities:[]}}), /Approved earning opportunities are not available yet/)
  const html=render(Earn,{catalogue:{ready:true,activities:[{code:'EXAMPLE',name:'<Approved policy>',
    category:'Test policy',kind:'individual',points:3,frequency:'daily'}]}})
  assert.match(html,/&lt;Approved policy&gt;/);assert.match(html,/3<small>points/)
  assert.match(html,/authorized officer verifies/);assert.match(html,/Viewing an activity does not award points/)
  assert.doesNotMatch(html,/Submitted|Pending Verification|Completed|<button|<form/)
})
test('catalogue projection is read-only, allowlisted and invoked only inside existing scoped score projection',()=>{
  const source=fs.readFileSync(new URL('../../../backend/dic/camper_catalogue.py',import.meta.url),'utf8')
  assert.doesNotMatch(source,/\.save\(|\.create\(|\.update\(|record_activity|ActivityAward|participant_id|enrollment/)
  assert.match(source,/edition_year != 2026 or not storage_ready/)
  const api=fs.readFileSync(new URL('../../../backend/dic/activity_scoring_api.py',import.meta.url),'utf8')
  assert.match(api,/authorized_grant\(request\)/);assert.match(api,/scoped_orders\(grant\)/)
  assert.match(api,/if not item:\s+raise NotFound/)
  assert.match(api,/result\['earn_points'\] = camper_catalogue\(edition.year, ready\)/)
})
