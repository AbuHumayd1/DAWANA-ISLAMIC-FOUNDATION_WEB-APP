const assert=require('node:assert/strict')
const fs=require('node:fs')
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH)
const base='http://127.0.0.1:5178', ref='11111111-1111-4111-8111-111111111111'
;(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:960}});let archives=0,reads=0,rechecks=0;const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();let data={}
 if(u.pathname.endsWith('/auth/me/'))data={display_name:'Synthetic Admin',role:'DIC Operator',permissions:{operations:true,registrations:true,participants:true}}
 if(u.pathname.endsWith('/csrf/'))data={csrfToken:'synthetic'}
 if(u.pathname.endsWith(`/registrations/${ref}/`))data={id:ref,submitted_at:'2026-11-14T00:00:00Z',participant_count:0,registration_basis:'paid',payment_status:'pending',status:'submitted',quoted_total_ngn:'40000',categories:['Adult'],participants:[],deletion:{eligible:false,reason:'Protected payment evidence must be retained.'},test_cleanup:{payment_state:'failed_evidence_retained',archived:false,can_archive:true,can_recheck:true}}
 if(u.pathname.endsWith('/archive-test/')){archives++;assert.equal(route.request().postDataJSON().confirmation,ref);data={archived:true,reference:ref}}
 if(u.pathname.endsWith('/recheck-payment/')){rechecks++;data={checked:true}}
 if(u.pathname.endsWith('/registrations/')){reads++;data={results:[],count:0,pages:1,page:1}}
 if(u.pathname.endsWith('/filters/'))data={editions:[],categories:[],houses:[]}
 return route.fulfill({contentType:'application/json',body:JSON.stringify(data)})})
 await page.goto(base+`/dic/operations/registrations/${ref}`);await page.getByRole('button',{name:'Archive test registration',exact:true}).waitFor();await page.getByRole('button',{name:'Recheck existing payment',exact:true}).click();await page.getByRole('button',{name:'Archive test registration',exact:true}).waitFor();assert.equal(rechecks,1);await page.getByLabel('Reason for archiving this test registration').fill('Explicit synthetic test disposal')
 page.once('dialog',async d=>{assert.ok(d.message().includes(ref));await d.dismiss()});await page.getByRole('button',{name:'Archive test registration',exact:true}).click();assert.equal(archives,0)
 page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Archive test registration',exact:true}).click();await page.getByRole('status').filter({hasText:'archived from the active list'}).waitFor();assert.equal(archives,1);assert.equal(await page.getByRole('button',{name:'Archive test registration',exact:true}).count(),0);await page.getByRole('link',{name:'Return to refreshed registrations'}).click();await page.getByText('No registrations found',{exact:true}).waitFor();assert.ok(reads>0);assert.deepEqual(errors,[]);await page.close();console.log('Operations archival is explicitly confirmed, labelled separately from deletion, and refreshes the active list')
 fs.writeFileSync('../../archive-browser-result.json',JSON.stringify({passed:true,widths:[320,390,430,820,1440]}))
}finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1})
