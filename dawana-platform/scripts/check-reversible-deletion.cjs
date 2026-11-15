/* Reversible deletion acceptance: offline API/provider fixtures only. */
const assert=require('node:assert/strict')
const fs=require('node:fs')
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH)
const base='http://127.0.0.1:5178', ref='11111111-1111-4111-8111-111111111111'
;(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 fs.mkdirSync('../../screenshots',{recursive:true})
 for(const width of [390,1440]){
 const page=await browser.newPage({viewport:{width,height:960}});const errors=[];page.on('pageerror',e=>errors.push(e.message));let deleted=false,archived=false,deleteRequests=0,restoreRequests=0,archiveRequests=0,confirmAction=true
 const record=()=>({id:ref,created_at:'2026-11-14T00:00:00Z',submitted_at:'2026-11-14T00:00:00Z',participant_count:0,categories:['Adult'],participants:[],quoted_total_ngn:'40000',payment_status:'failed',status:'submitted',registration_basis:'paid',record_state:deleted?'deleted':archived?'archived':'normal',deleted_at:deleted?'2026-11-14T01:00:00Z':null,deletion:{eligible:!deleted,reason:deleted?'Already in Trash.':'',reversible:true},restore:{eligible:deleted,reason:''},test_cleanup:{can_archive:!deleted,archived,archive_reason:deleted?'Restore from Trash first.':'',payment_state:'failed_evidence_retained',can_recheck:false}})
 const other={...record(),id:'22222222-2222-4222-8222-222222222222',payment_status:'pending',deletion:{eligible:true,reason:''},test_cleanup:{can_archive:true,archive_reason:''}}
 const paid={...other,id:'33333333-3333-4333-8333-333333333333',payment_status:'paid',verified_paid:true,deletion:{eligible:true,reason:''}}
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();let data={}
 if(u.pathname.endsWith('/auth/me/'))data={display_name:'Synthetic Administrator',role:'DIC Operator',permissions:{operations:true,registrations:true,participants:true,registration_cleanup:true}}
 if(u.pathname.endsWith('/csrf/'))data={csrfToken:'synthetic-csrf'}
 if(u.pathname.endsWith(`/registrations/${ref}/`))data=record()
 if(u.pathname.endsWith('/delete/')){assert.equal(route.request().postDataJSON().confirmation,ref);deleteRequests++;deleted=true;data={deleted:true,reversible:true,reference:ref}}
 if(u.pathname.endsWith('/restore-deleted/')){restoreRequests++;deleted=false;archived=false;data={restored:true,reference:ref}}
 if(u.pathname.endsWith('/archive-test/')){archiveRequests++;archived=true;data={archived:true,reference:ref}}
 if(u.pathname.endsWith('/registrations/')){const trash=u.searchParams.get('archive')==='trash',all=u.searchParams.get('archive')==='all';const results=trash?(deleted?[record()]:[]):[...(!deleted&&(all||!archived)?[record()]:[]),other,paid];data={results,count:results.length,pages:1,page:1}}
 if(u.pathname.endsWith('/filters/'))data={editions:[],categories:[],houses:[]}
 return route.fulfill({contentType:'application/json',body:JSON.stringify(data)})})
 page.on('dialog',async dialog=>{
 assert.ok(dialog.message().includes(ref))
 if(dialog.type()==='prompt')await dialog.accept('Owner selected synthetic unpaid test')
 else{if(dialog.message().startsWith('Delete')){assert.ok(dialog.message().includes('Trash'));assert.ok(dialog.message().includes('restore'))}if(confirmAction)await dialog.accept();else await dialog.dismiss()}
 })
 const row=()=>page.locator('tbody tr').filter({hasText:'11111111-1111'})
 await page.goto(base+'/dic/operations/registrations');await row().getByRole('button',{name:'Delete',exact:true}).waitFor()
 assert.equal(await row().getByRole('button',{name:'Archive',exact:true}).isEnabled(),true)
 assert.equal(await page.locator('tbody tr').filter({hasText:'33333333-3333'}).getByRole('button',{name:'Delete',exact:true}).isEnabled(),true)
 confirmAction=false;await row().getByRole('button',{name:'Delete',exact:true}).click();assert.equal(deleteRequests,0)
 confirmAction=true;await row().getByRole('button',{name:'Delete',exact:true}).click();await page.locator('p[role=status]').filter({hasText:'Delete completed'}).waitFor();await page.waitForFunction(()=>document.querySelectorAll('tbody tr').length===2);assert.equal(await row().count(),0);assert.equal(deleteRequests,1)
 await page.getByRole('link',{name:'Trash / Restore deleted registrations',exact:true}).click();await row().getByRole('button',{name:'Restore',exact:true}).waitFor();assert.equal(await row().getByRole('button',{name:'Delete',exact:true}).isDisabled(),true)
 await page.screenshot({path:`../../screenshots/trash-actions-${width}.png`})
 await row().getByRole('link').first().click();await page.getByRole('heading',{name:'Registration in Trash'}).waitFor();await page.getByRole('button',{name:'Restore',exact:true}).click();await page.getByRole('status').filter({hasText:'was restored from Trash'}).waitFor();assert.equal(restoreRequests,1)
 await page.getByRole('link',{name:'Return to refreshed registrations',exact:true}).click();await row().getByRole('button',{name:'Archive',exact:true}).waitFor();await row().getByRole('button',{name:'Archive',exact:true}).click();await page.locator('p[role=status]').filter({hasText:'Archive completed'}).waitFor();await page.waitForFunction(()=>document.querySelectorAll('tbody tr').length===2);assert.equal(archiveRequests,1)
 await page.getByRole('link',{name:'All non-deleted registrations',exact:true}).click();await row().getByRole('button',{name:'Delete',exact:true}).waitFor();assert.equal(await row().getByRole('button',{name:'Archive',exact:true}).isDisabled(),true)
 await row().getByRole('link').first().click();await page.getByRole('button',{name:'Delete registration',exact:true}).waitFor();await page.getByLabel('Reason for deleting this registration').fill('Owner selected synthetic test')
 await page.getByRole('button',{name:'Delete registration',exact:true}).click();await page.getByRole('status').filter({hasText:'was moved to Trash'}).waitFor();assert.equal(deleteRequests,2)
 assert.deepEqual(errors,[]);await page.close();console.log(`${width}: row Delete/Archive, cancel/confirm, Trash, detail Restore, old-link consequence and separate Archive behavior passed`)
 }
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1})
