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
  for (const label of ['PVC card','A6 badge','PDF badge']) assert.ok(html.includes(label))
  assert.equal((html.match(/download=1/g)||[]).length,1)
  const source = fs.readFileSync(new URL('../components/dic/DigitalIDPresentation.jsx',import.meta.url),'utf8')
  assert.match(source,/\['portrait','PDF badge'\]/)
  assert.match(source,/setFormat\(key\)/)
  assert.doesNotMatch(html,/id-action-panel|id-format-row/)
  const staff = render(ID, { card: { id, name: 'Synthetic camper', participant_number: 'TEST' }, staff: true, onClose() {} })
  for (const [markup, pathname] of [
    [html, `/api/v1/dic/participant/enrollments/${id}/card/`],
    [staff, `/api/v1/dic/ids/cards/${id}/`],
  ]) {
    const preview = markup.match(/<a\b([^>]+)>Open &amp; print<\/a>/)
    assert.ok(preview, 'Selected PVC print link must be present')
    const href = preview[1].match(/\bhref="([^"]+)"/)
    assert.ok(href, 'Preview must navigate to its protected document')
    // Local builds use relative URLs; production uses the configured HTTPS API.
    const url = new URL(href[1].replaceAll('&amp;', '&'), 'https://api.dawanaislamicfoundation.org')
    assert.ok(['https://api.dawanaislamicfoundation.org', 'https://api.example.test'].includes(url.origin))
    assert.equal(url.pathname, pathname)
    assert.deepEqual([...url.searchParams], [['format', 'pvc'], ...(markup === staff ? [['return_to', 'operations']] : [])])
    assert.equal(url.hash, '')
    assert.equal(url.username, ''); assert.equal(url.password, '')
    assert.match(preview[1], /referrerPolicy="no-referrer"/i)
  }
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

test('Digital ID inherits saved Camper appearance without affecting staff documents', () => {
  const portal = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx',import.meta.url),'utf8')
  const css = fs.readFileSync(new URL('../components/dic/DigitalIDPresentation.css',import.meta.url),'utf8')
  assert.match(portal,/localStorage\.getItem\('dic-camper-appearance'\)/)
  assert.match(portal,/data-theme=\{card \? cardTheme : undefined\}/)
  assert.match(css,/\.cp-route \.participant-portal\[data-theme=dark\] \.id-card-workspace/)
  assert.match(css,/\.cp-route \.participant-portal\[data-theme=dark\] \.id-format-tabs button/)
  assert.match(css,/\.cp-route \.participant-portal\[data-theme=dark\] \.id-card-actions \.id-download-action/)
  assert.doesNotMatch(portal,/setCard\(\{ \.\.\.data, id,.*cardTheme/)
})
test('Participant sign-in refinement retains credential flow and recovery actions', () => {
  const portal = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx',import.meta.url),'utf8')
  const css = fs.readFileSync(new URL('../pages/ParticipantPortal.css',import.meta.url),'utf8')
  assert.match(portal,/className="cp-auth-title"/)
  assert.match(portal,/className="cp-auth-panel-header"/)
  assert.match(portal,/onLogin=\{passwordLogin\}/)
  assert.match(portal,/onRecover=\{recoverAccount\}/)
  assert.match(portal,/onVerify=\{\(\) =>/)
  assert.match(css,/\.cp-route \.cp-auth \.participant-access-panel \{[^}]*box-shadow:/)
  assert.match(css,/\.cp-route \.cp-auth \.cp-account-login form input:not\(\[type=checkbox\]\)/)
})
