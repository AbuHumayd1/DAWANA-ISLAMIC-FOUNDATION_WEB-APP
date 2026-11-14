const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH)
const base = 'http://127.0.0.1:5178'
;(async () => {
 const browser=await chromium.launch({channel:'chrome',headless:true})
 try {
 for(const width of [320,390,430,820,1440]) {
 const page=await browser.newPage({viewport:{width,height:900}})
 const errors=[];page.on('pageerror', e=>errors.push(e.message))
 await page.route('**/*',route=>{
 const u=new URL(route.request().url());if(u.origin!==base)return route.abort()
 if(!u.pathname.startsWith('/api/'))return route.continue()
 let body={experiences:[],introductions:[],channels:[]}
 if(u.pathname.endsWith('/payments/return/')) body={order:{order_id:'11111111-1111-4111-8111-111111111111',status:'confirmed',payment_status:'paid',total_amount_ngn:'40000',processing:{housing:'ready'},participants:[{name:'Synthetic Participant',category:'Graduates & Adults'}]}}
 if(u.pathname.endsWith('/csrf/')) body={csrfToken:'synthetic'}
 if(u.pathname.endsWith('/orders/')) { const data=route.request().postDataJSON();assert.equal(data.portal_account.mode,'existing');body={order_id:'11111111-1111-4111-8111-111111111111',access_token:'synthetic-only',payment_status:'paid',total_amount_ngn:'40000',items:[{category_name:'Graduates & Adults',fee_ngn:'40000',price_type:'regular'}]} }
 if(u.pathname.endsWith('/registration-options/'))body={name:'Darul Islam Camp 2026',general_information:{theme:'The Outliers'},registration_is_open:true,camp_start_date:'2026-12-23',camp_end_date:'2027-01-01',venue:'Fazil Umar Secondary School, Lagos',housing_age_reference_date:'2026-12-23',categories:[{id:1,name:'Graduates & Adults',current_fee_ngn:'40000',regular_fee_ngn:'40000'}]}
 return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})
 })
 async function shot(stage){await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:`../output/mobile-design/${width}-${stage}.png`,fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),JSON.stringify(await page.locator('body *').evaluateAll(nodes=>nodes.filter(n=>n.getBoundingClientRect().right>innerWidth+1).map(n=>[n.tagName,n.className,n.getBoundingClientRect().right]).slice(0,20))))}
 await page.goto(base+'/dic');await page.getByRole('button',{name:/Register for DIC/}).first().waitFor();await page.locator('.dic-camp-brief').getByText('Fazil Umar Secondary School, Lagos',{exact:true}).waitFor();assert.match(await page.locator('h1').innerText(),/THE OUTLIERS/i);await shot('landing')
 await page.getByRole('button',{name:/Register for DIC/}).first().click()
 await page.getByLabel('Booking contact name',{exact:true}).fill('Synthetic Contact');await page.getByLabel('Booking email',{exact:true}).fill('synthetic@example.test')
 await page.locator('#fullName').fill('Synthetic Participant');await page.locator('#address').fill('Synthetic address');await page.locator('#phone').fill('08000000000')
 async function choose(label,index){const box=page.getByRole('combobox',{name:label});await box.focus();await box.press('Home');await box.press('Home');for(let i=0;i<index;i++)await box.press('ArrowDown');await box.press('Enter')}
 await choose(/Age and date-of-birth/,0);await page.locator('#dob').fill('2011-12-24');assert.equal(await page.getByLabel('Parent or guardian phone',{exact:true}).getAttribute('required'),'')
 await page.locator('#dob').fill('2010-12-23');assert.equal(await page.getByLabel('Parent or guardian phone',{exact:true}).count(),0)
 await choose(/Age and date-of-birth/,2)
 await page.locator('input[name=sex][value=Male]').check()
 await choose(/Academic Status/,0);await choose(/Occupation/,0);await choose(/Marital Status/,0)
 await page.locator('input[name=categoryId][value="1"]').check();assert.equal(await page.locator('input[type=email]').count(),1);await shot('form')
 assert.equal(await page.locator('.dic-steps > div').count(),4)
 await page.getByRole('button',{name:/Continue to summary/}).click();await page.getByRole('heading',{name:'Registered participants'}).waitFor();await shot('review')
 await page.getByRole('button',{name:/Continue to checkout/}).click();await page.getByRole('heading',{name:'Checkout',exact:true}).waitFor();assert.equal(await page.locator('input[type=email]').count(),0);assert.ok((await page.locator('.checkout-box').innerText()).includes('synthetic@example.test'))
 await page.getByLabel('Account option').selectOption('existing');await page.getByLabel('Existing password',{exact:true}).waitFor();assert.equal(await page.getByLabel('Confirm password',{exact:true}).count(),0);await shot('checkout')
 await page.getByLabel('Username',{exact:true}).fill('synthetic-owner');await page.getByLabel('Existing password',{exact:true}).fill('synthetic-password');await page.getByRole('button',{name:'Pay Now',exact:true}).click();await page.getByRole('heading',{name:'DIC registration confirmed'}).waitFor({timeout:5000}).catch(async e=>{console.log(page.url(),errors,await page.locator('body').innerText());throw e});await shot('confirmation');assert.deepEqual(errors,[]);await page.close();console.log(`${width}: landing, form, guardian boundaries, review, checkout, confirmation passed`)
 }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1})
