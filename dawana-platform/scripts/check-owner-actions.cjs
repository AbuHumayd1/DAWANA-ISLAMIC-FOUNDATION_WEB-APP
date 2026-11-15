/* Offline browser acceptance; PostgreSQL API tests cover real state transitions. */
const assert=require('node:assert/strict')
const fs=require('node:fs')
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH)
const base='http://127.0.0.1:5178'
;(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 fs.mkdirSync('../../screenshots',{recursive:true})
 for(const width of [390,1440]){
 const page=await browser.newPage({viewport:{width,height:960}}), errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 const states=['pending','failed','mismatch','attempt-linked','paid']
 const records=states.map((state,index)=>({id:`${String(index+1).repeat(8)}-1111-4111-8111-111111111111`,state,deleted:false,archived:false}))
 let mutations=0,confirmAction=true
 const data=r=>({id:r.id,created_at:'2026-11-15T00:00:00Z',participant_count:0,categories:[r.state],participants:[],quoted_total_ngn:'18000',payment_status:r.state==='paid'?'paid':r.state==='failed'?'failed':'pending',status:'submitted',registration_basis:'paid',record_state:r.deleted?'deleted':r.archived?'archived':'normal',deleted_at:r.deleted?'2026-11-15T01:00:00Z':null,deletion:{eligible:!r.deleted,reason:r.deleted?'Already in Trash.':'',reversible:true},restore:{eligible:r.deleted,reason:''},test_cleanup:{can_archive:!r.deleted,can_unarchive:!r.deleted&&r.archived,archived:r.archived,archive_reason:'',payment_state:r.state==='mismatch'?'reconciliation_required':'payment_in_progress_or_unknown',can_recheck:false}})
 await page.route('**/*',route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();let body={}
 if(u.pathname.endsWith('/auth/me/'))body={display_name:'Synthetic Administrator',role:'DIC Operator',permissions:{operations:true,registrations:true,participants:true,registration_cleanup:true}}
 if(u.pathname.endsWith('/csrf/'))body={csrfToken:'synthetic-csrf'}
 const r=records.find(r=>u.pathname.includes(r.id))
 if(r){body=data(r);if(req.method()==='POST'){
 assert.equal(req.headers()['x-csrftoken'],'synthetic-csrf');assert.equal(req.postDataJSON().confirmation,r.id);assert.ok(req.postDataJSON().reason)
 mutations++
 if(u.pathname.endsWith('/delete/'))r.deleted=true
 if(u.pathname.endsWith('/restore-deleted/')){r.deleted=false;r.archived=false}
 if(u.pathname.endsWith('/archive-test/'))r.archived=true
 if(u.pathname.endsWith('/unarchive/'))r.archived=false
 body={reference:r.id,deleted:r.deleted,archived:r.archived}
 }}
 if(u.pathname.endsWith('/registrations/')){const view=u.searchParams.get('archive')||'active';const results=records.filter(r=>view==='trash'?r.deleted:!r.deleted&&(view==='all'||(view==='archived'?r.archived:!r.archived))).map(data);body={results,count:results.length,pages:1,page:1}}
 if(u.pathname.endsWith('/filters/'))body={categories:[],houses:[]}
 return route.fulfill({contentType:'application/json',body:JSON.stringify(body)})})
 page.on('dialog',async d=>{assert.ok(records.some(r=>d.message().includes(r.id)));if(d.type()==='prompt')await d.accept('Explicit synthetic owner action');else if(confirmAction)await d.accept();else await d.dismiss()})
 const row=r=>page.locator('tbody tr').filter({hasText:r.id.slice(0,8)})
 await page.goto(base+'/dic/operations/registrations?payment_status=pending')
 for(const r of records){await row(r).getByRole('button',{name:'Delete',exact:true}).waitFor();assert.equal(await row(r).getByRole('button',{name:'Delete',exact:true}).isEnabled(),true);assert.equal(await row(r).getByRole('button',{name:'Archive',exact:true}).isEnabled(),true)}
 confirmAction=false;await row(records[0]).getByRole('button',{name:'Delete',exact:true}).click();assert.equal(mutations,0);confirmAction=true
 for(const r of records){
 await row(r).getByRole('button',{name:'Delete',exact:true}).click();await row(r).waitFor({state:'detached'})
 await page.getByRole('link',{name:'Trash / Restore deleted registrations',exact:true}).click();await row(r).getByRole('button',{name:'Restore',exact:true}).waitFor()
 await row(r).getByRole('link').first().click();await page.getByRole('heading',{name:'Registration in Trash'}).waitFor();await page.getByRole('button',{name:'Restore',exact:true}).click();await page.getByRole('status').filter({hasText:'was restored from Trash'}).waitFor()
 await page.getByRole('link',{name:'Return to refreshed registrations',exact:true}).click();await row(r).getByRole('button',{name:'Delete',exact:true}).waitFor()
 console.log(`${width}: ${r.state} enabled Delete, confirmation, removal, Trash and detail Restore passed`)
 }
 const r=records[0]
 await row(r).getByRole('button',{name:'Archive',exact:true}).click();await row(r).waitFor({state:'detached'})
 await page.getByRole('link',{name:'Archived registrations',exact:true}).click();await row(r).getByRole('button',{name:'Unarchive',exact:true}).waitFor()
 await page.screenshot({path:`../../screenshots/archived-actions-${width}.png`})
 await row(r).getByRole('button',{name:'Unarchive',exact:true}).click();await row(r).waitFor({state:'detached'})
 await page.getByRole('link',{name:'Active registrations',exact:true}).click();await row(r).getByRole('link').first().click()
 await page.getByLabel('Reason for archiving this registration').fill('Explicit detail archive')
 await page.getByRole('button',{name:'Archive registration',exact:true}).click();await page.getByRole('status').filter({hasText:'was archived'}).waitFor()
 await page.getByRole('link',{name:'Return to refreshed registrations',exact:true}).click();await page.getByRole('link',{name:'Archived registrations',exact:true}).click();await row(r).getByRole('link').first().click()
 await page.getByLabel('Reason for unarchiving this registration').fill('Explicit detail unarchive');await page.getByRole('button',{name:'Unarchive registration',exact:true}).click();await page.getByRole('status').filter({hasText:'was unarchived'}).waitFor()
 assert.deepEqual(errors,[]);assert.equal(mutations,14);await page.close();console.log(`${width}: row and detail Archive/Unarchive, refresh and independent archived view passed`)
 }
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1})
