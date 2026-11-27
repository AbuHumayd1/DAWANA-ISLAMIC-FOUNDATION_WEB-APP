/* Synthetic browser acceptance for both public photo mosaics. Start Vite on 127.0.0.1:5178. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178'
const photos = Array.from({length:11},(_,i)=>({
  source_kind:'photos',url:'/api/v1/dic/mock-photo/'+(i+1),
  title:'Synthetic caption '+(i+1),alt_text:'Synthetic photograph '+(i+1),
}))
const pixel=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')

;(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true})
  try {
    const page=await browser.newPage()
    const errors=[]
    let empty=false, mutations=0
    page.on('pageerror',error=>errors.push(error.message))
    await page.route('**/*',route=>{
      const request=route.request(),url=new URL(request.url())
      if(url.origin!==base)return route.abort()
      if(request.method()!=='GET'){mutations++;return route.abort()}
      if(url.pathname==='/api/v1/dic/studio/public-placements/'){
        return route.fulfill({json:{items:!empty&&url.searchParams.get('view')==='photos'?photos:[],has_more:false}})
      }
      if(url.pathname.startsWith('/api/v1/dic/mock-photo/'))return route.fulfill({contentType:'image/png',body:pixel})
      if(url.pathname.includes('/registration-options/'))return route.fulfill({json:{name:'Synthetic edition',camp_start_date:'2026-12-23',camp_end_date:'2027-01-01',registration_is_open:false,categories:[]}})
      if(url.pathname.startsWith('/api/'))return route.fulfill({status:404,json:{}})
      return route.continue()
    })
    for(const path of ['/','/dic']){
      await page.goto(base+path)
      const mosaic=page.locator('.photo-mosaic')
      await mosaic.waitFor()
      assert.equal(await mosaic.locator('.photo-mosaic-tile').count(),9)
      assert.equal(await mosaic.locator('.photo-mosaic-tile img[loading=lazy]').count(),9)
      assert.equal(await mosaic.locator('.photo-mosaic-tile').first().innerText(),'')
      for(const width of [320,360,390,430,768,1024,1440]){
        await page.setViewportSize({width,height:900})
        const grid=mosaic.locator('.photo-mosaic-grid')
        await grid.scrollIntoViewIfNeeded()
        assert.equal(await grid.evaluate(el=>el.scrollWidth<=el.clientWidth),true,'Overflow at '+width)
        if(width<=700){
          const positions=await grid.locator('button').evaluateAll(els=>els.slice(0,3).map(el=>{
            const r=el.getBoundingClientRect()
            return {x:r.x,y:r.y,w:r.width}
          }))
          assert.ok(positions[0].w>positions[1].w*1.8)
          assert.ok(Math.abs(positions[1].y-positions[2].y)<2)
        }
        const opener=mosaic.locator('.photo-mosaic-tile').first()
        await opener.click()
        const viewer=mosaic.locator('dialog')
        await viewer.waitFor()
        assert.equal(await viewer.locator('img').getAttribute('alt'),'Synthetic photograph 1')
        await page.keyboard.press('ArrowRight')
        assert.equal(await viewer.locator('img').getAttribute('alt'),'Synthetic photograph 2')
        await page.keyboard.press('Escape')
        assert.equal(await viewer.isVisible(),false)
        assert.equal(await opener.evaluate(el=>el===document.activeElement),true)
      }
      await page.emulateMedia({reducedMotion:'reduce'})
      assert.equal(await mosaic.locator('.photo-mosaic-tile img').first().evaluate(el=>getComputedStyle(el).transitionDuration),'0s')
      empty=true
      await Promise.all([page.waitForResponse(res=>res.url().includes('view=photos')),page.reload()])
      await page.locator('.photo-mosaic').waitFor({state:'hidden'})
      assert.equal(await page.locator('.photo-mosaic-tile').count(),0)
      empty=false
    }
    assert.equal(mutations,0)
    assert.deepEqual(errors,[])
    console.log('PASS: homepage and camp mosaics, nine-photo cap, no visible captions, seven viewport sizes, viewer navigation/focus, reduced motion and empty feed.')
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1})
