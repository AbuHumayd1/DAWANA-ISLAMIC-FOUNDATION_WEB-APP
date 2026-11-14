/* Synthetic-only browser acceptance. No external or production request is allowed. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH)
const fs = require('node:fs')
const base='http://127.0.0.1:5178', ref='11111111-1111-4111-8111-111111111111'
;(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true})
 try {
 for(const width of [320,390,430,820,1440]) {
 const page=await browser.newPage({viewport:{width,height:960}});await page.emulateMedia({reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();let data={authenticated:false,channels:[],experiences:[],introductions:[]};if(u.pathname.endsWith('/capabilities/'))data={accounts:{enabled:true},session:{remember_seconds:28800}};return route.fulfill({contentType:'application/json',body:JSON.stringify(data)})})
 await page.goto(base);await page.locator('#what-we-do .area-card').first().waitFor();const cols=await page.locator('#what-we-do .area-grid').evaluate(n=>getComputedStyle(n).gridTemplateColumns.split(' ').length);assert.equal(cols,width<=600?1:width<=1000?2:3)
 await page.locator('#what-we-do').evaluate(n=>n.scrollIntoView({behavior:'instant',block:'start'}));await page.waitForFunction(()=>document.querySelector('#what-we-do').getBoundingClientRect().top < 200);await page.waitForTimeout(800);await page.screenshot({path:`../../home-${width}.png`});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width} homepage overflow`)
 await page.goto(base+'/dic/participant');const link=page.getByRole('link',{name:'Back to DAWANA Website',exact:true});await link.waitFor();assert.equal(await link.getAttribute('href'),'/');await page.screenshot({path:`../../logout-${width}.png`});await link.click();await page.waitForURL(base+'/');assert.deepEqual(errors,[]);await page.close();console.log(`${width}: homepage columns, overflow and logged-out website link passed`)
 }
 for(const allowed of [true,false]) {
 const page=await browser.newPage({viewport:{width:390,height:900}});let checks=0
 await page.addInitScript(({ref})=>sessionStorage.setItem('dawana.dic.registration.v1',JSON.stringify({participants:[],orderId:ref,idempotencyKey:'22222222-2222-4222-8222-222222222222',expiresAt:1,paymentStatus:'pending',submissionUncertain:false})),{ref})
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();let data={};let status=200
 if(u.pathname.endsWith('/registration-options/'))data={name:'Synthetic camp',registration_is_open:true,categories:[{id:1,name:'Adult',current_fee_ngn:'40000'}]}
 if(u.pathname.endsWith('/restart-check/')){checks++;assert.deepEqual(route.request().postDataJSON(),{identifier:'synthetic-owner',password:'synthetic-password'});data=allowed?{safe_to_restart:true}:{detail:'Payment may still succeed. Do not pay again.'};status=allowed?200:400}
 return route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})})
 await page.goto(base+'/dic/register/checkout');await page.getByRole('heading',{name:'Check your existing payment'}).waitFor();assert.equal(await page.locator('#fullName').count(),0);await page.getByLabel('Account username',{exact:true}).fill('synthetic-owner');await page.getByLabel('Account password',{exact:true}).fill('synthetic-password');await page.getByRole('button',{name:'Check and start fresh'}).click();if(allowed)await page.locator('#fullName').waitFor();else{await page.getByRole('alert').waitFor();assert.equal(await page.locator('#fullName').count(),0)}assert.equal(checks,1);await page.close()
 }
 console.log('Expired order hint preserved; authorized unused-order restart allowed; payment uncertainty blocks restart')
 const page=await browser.newPage({viewport:{width:1440,height:960}});let deletes=0,reads=0;const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();let data={}
 if(u.pathname.endsWith('/auth/me/'))data={display_name:'Synthetic Admin',role:'DIC Operator',permissions:{operations:true,registrations:true,participants:true}}
 if(u.pathname.endsWith('/csrf/'))data={csrfToken:'synthetic'}
 if(u.pathname.endsWith(`/registrations/${ref}/`))data={id:ref,submitted_at:'2026-11-14T00:00:00Z',participant_count:0,registration_basis:'paid',payment_status:'pending',status:'submitted',quoted_total_ngn:'40000',categories:['Adult'],participants:[],deletion:{eligible:true,reason:''}}
 if(u.pathname.endsWith('/delete/')){deletes++;assert.equal(route.request().postDataJSON().confirmation,ref);data={deleted:true,reference:ref}}
 if(u.pathname.endsWith('/registrations/')){reads++;data={results:[],count:0,pages:1,page:1}}
 if(u.pathname.endsWith('/filters/'))data={editions:[],categories:[],houses:[]}
 return route.fulfill({contentType:'application/json',body:JSON.stringify(data)})})
 await page.goto(base+`/dic/operations/registrations/${ref}`);await page.getByRole('button',{name:'Delete registration',exact:true}).waitFor();await page.getByLabel('Reason for deleting this test registration').fill('Explicit synthetic test disposal')
 page.once('dialog',async d=>{assert.ok(d.message().includes(ref));await d.dismiss()});await page.getByRole('button',{name:'Delete registration',exact:true}).click();assert.equal(deletes,0)
 page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Delete registration',exact:true}).click();await page.getByRole('status').filter({hasText:'permanently deleted'}).waitFor();assert.equal(deletes,1);assert.equal(await page.getByRole('button',{name:'Delete registration',exact:true}).count(),0);await page.getByRole('link',{name:'Return to refreshed registrations'}).click();await page.getByText('No registrations found',{exact:true}).waitFor();assert.ok(reads>0);assert.deepEqual(errors,[]);await page.close();console.log('Operations explicit confirmation, cancellation, permanent deletion success and refreshed empty list passed')
 fs.writeFileSync('../../browser-result.json',JSON.stringify({passed:true,widths:[320,390,430,820,1440]}))
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1})
