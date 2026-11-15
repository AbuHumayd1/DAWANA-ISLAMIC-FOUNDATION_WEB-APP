/* Paired with dic.owner_browser_acceptance: real synthetic Django backend. */
const assert=require('node:assert/strict')
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH)
const base='http://127.0.0.1:5178', api=process.env.OWNER_TEST_API
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(api||''))throw new Error('Disposable loopback API required')
const records=JSON.parse(process.env.OWNER_TEST_RECORDS)
;(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 for(const width of [390,1440]){
 const context=await browser.newContext({viewport:{width,height:960}})
 await context.addCookies([{name:'sessionid',value:process.env.OWNER_TEST_SESSION,url:base,httpOnly:true,sameSite:'Lax'}])
 const page=await context.newPage(), errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue()
 const response=await route.fetch({url:api+u.pathname+u.search});return route.fulfill({response})})
 let confirm=true
 page.on('dialog',d=>{assert.equal(d.type(),'confirm');return confirm?d.accept():d.dismiss()})
 const row=r=>page.locator('tbody tr').filter({hasText:r.id.slice(0,8)})
 await page.goto(base+'/dic/operations/registrations')
 for(const r of records){
 const button=row(r).getByRole('button',{name:'Delete',exact:true});await button.waitFor();assert.equal(await button.isEnabled(),true)
 if(r===records[0]){confirm=false;await button.click();assert.equal(await row(r).count(),1);confirm=true}
 await button.click();await row(r).waitFor({state:'detached'})
 await page.getByRole('link',{name:'Trash / Restore deleted registrations',exact:true}).click();await row(r).getByRole('button',{name:'Restore',exact:true}).click();await row(r).waitFor({state:'detached'})
 await page.getByRole('link',{name:'Active registrations',exact:true}).click();await row(r).getByRole('button',{name:'Archive',exact:true}).click();await row(r).waitFor({state:'detached'})
 await page.getByRole('link',{name:'Archived registrations',exact:true}).click();await row(r).getByRole('button',{name:'Unarchive',exact:true}).click();await row(r).waitFor({state:'detached'})
 await page.getByRole('link',{name:'Active registrations',exact:true}).click();await row(r).getByRole('button',{name:'Delete',exact:true}).waitFor()
 console.log(`${width}: REAL API ${r.state}: Delete/Trash/Restore and Archive/Unarchive passed`)
 }
 assert.deepEqual(errors,[]);await context.close()
 }
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1})
