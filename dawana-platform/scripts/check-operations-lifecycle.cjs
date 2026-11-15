/* Real Django LiveServer fixture; never forwards requests outside loopback. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178', api = process.env.OWNER_TEST_API
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(api || '')) throw new Error('Disposable loopback API required')
const records = JSON.parse(process.env.LIFECYCLE_RECORDS), edition = process.env.LIFECYCLE_EDITION
;(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : {}) })
  try {
    for (const width of [390, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } })
      const page = await context.newPage(), errors = []
      page.setDefaultTimeout(25000)
      page.on('pageerror', error => { errors.push(error.message); console.log('Browser error:',error.message) })
      page.on('dialog', dialog => dialog.accept())
      let queue = Promise.resolve()
      await page.route('**/*', async route => {
        const url = new URL(route.request().url())
        if (url.origin !== base) return route.abort()
        if (!url.pathname.startsWith('/api/')) return url.origin === base ? route.continue() : route.abort()
        const task = queue.then(async () => {
          const headers = { ...route.request().headers() }
          const cookies = (headers.cookie || '').split(';').filter(s => !s.trim().startsWith('sessionid=')).filter(Boolean)
          headers.cookie = [...cookies, 'sessionid=' + process.env.OWNER_TEST_SESSION].join('; ')
          const response = await route.fetch({ url: api + url.pathname + url.search, headers, timeout: 30000 })
          return route.fulfill({ response })
        })
        queue = task.catch(() => {})
        try { await task } catch (error) { console.error(error.message); await route.abort().catch(() => {}) }
      })
      const get = path => page.evaluate(async path => {
        const response = await fetch('/api/v1/dic/operations' + path)
        if (!response.ok) throw new Error('API ' + response.status + ' ' + path)
        return response.json()
      }, path)
      const verify = async count => {
        const check = await get(`/check-in/?edition=${edition}`)
        const ids = await get('/enrollments/')
        const finance = await get(`/finance/?edition=${edition}`)
        assert.equal(check.totals.registered, count)
        assert.equal(ids.count, count)
        assert.equal(finance.summary.net_position_kobo, 400000)
        assert.equal(finance.summary.recorded_adjustments_kobo, 0)
      }
      const scope = view => page.getByRole('navigation', { name: 'Registration records', exact: true }).locator(`a${view === 'active' ? ':not([href*="archive="])' : `[href*="archive=${view}"]`}`)
      const act = async (id, action) => {
        const pending = page.waitForResponse(response => response.request().method() === 'POST' && response.url().includes(id))
        await row(id).getByRole('button', { name: action, exact: true }).click()
        const response = await pending
        assert.equal(response.status(), 200, await response.text())
      }
      const row = id => page.locator('tbody tr').filter({ hasText: id.slice(0, 8) })
      await page.goto(base + '/dic/operations/registrations?archive=trash')
      await row(records.unpaid).waitFor(); await verify(2)
      for (const id of [records.unpaid, records.paid]) {
        await scope('trash').click(); await act(id, 'Restore')
        await row(id).waitFor({ state: 'detached' }); await verify(4)
        await scope('active').click(); await act(id, 'Archive')
        await row(id).waitFor({ state: 'detached' }); await verify(2)
        await scope('archived').click(); await act(id, 'Unarchive')
        await row(id).waitFor({ state: 'detached' }); await verify(4)
        await scope('active').click(); await act(id, 'Delete')
        await row(id).waitFor({ state: 'detached' }); await verify(2)
      }
      await page.goto(base + '/dic/operations/check-in')
      await page.getByRole('heading', { name: 'Active Camper', exact: true }).waitFor()
      assert.equal(await page.getByRole('heading', { name: 'Deleted Unpaid', exact: true }).count(), 0)
      const totals = page.getByRole('region', { name: 'Check-in totals' })
      // section has an accessible name and is exposed as a region.
      assert.match(await totals.innerText(), /Registered\s+2/)
      assert.match(await totals.innerText(), /Checked In\s+1/)
      await page.getByRole('link', { name: 'Administrative check-in history', exact: true }).click()
      await page.getByRole('heading', { name: 'Historical Paid', exact: true }).waitFor()
      assert.equal(await page.getByRole('button', { name: 'Check In', exact: true }).count(), 0)
      await page.screenshot({ path: `../checkin-history-${width}.png`, fullPage: true })
      await page.goto(base + '/dic/operations/participant-ids')
      await page.getByRole('heading', { name: 'Active Camper', exact: true }).waitFor()
      assert.equal(await page.getByRole('heading', { name: 'Historical Paid', exact: true }).count(), 0)
      await page.getByRole('link', { name: 'Administrative ID history', exact: true }).click()
      await page.getByRole('heading', { name: 'Historical Paid', exact: true }).waitFor()
      assert.equal(await page.getByRole('button', { name: 'Replace ID', exact: true }).count(), 0)
      await page.screenshot({ path: `../id-history-${width}.png`, fullPage: true })
      await page.goto(base + `/dic/operations/finance?edition=${edition}`)
      await page.getByRole('heading', { name: 'Recent transactions', exact: true }).waitFor()
      assert.match(await page.getByRole('region', { name: 'Finance overview' }).innerText(), /4,000\.00/)
      assert.ok(await page.getByRole('columnheader', { name: 'amount (NGN)', exact: true }).count())
      assert.ok(await page.getByRole('cell', { name: 'Deleted', exact: true }).count())
      await page.screenshot({ path: `../finance-lifecycle-${width}.png`, fullPage: true })
      await page.goto(base + '/dic/operations/payments')
      await page.getByRole('columnheader', {name:'Registration lifecycle',exact:true}).waitFor()
      assert.ok(await page.getByRole('cell',{name:'Deleted',exact:true}).count())
      await page.goto(base + `/dic/operations/reporting-hub?edition=${edition}&domain=finance`)
      await page.getByText('Historical records; all registration lifecycle states',{exact:true}).waitFor()
      assert.ok(await page.getByRole('cell',{name:'deleted',exact:true}).count())
      const attendance = await get(`/reporting/?edition=${edition}&domain=attendance`)
      assert.match(attendance.scope_label, /Historical/)
      const overview = await get(`/reporting/?edition=${edition}&domain=registration`)
      assert.match(overview.scope_label, /Active/)
      const financeReport = await get(`/reporting/?edition=${edition}&domain=finance`)
      assert.ok(financeReport.rows.some(row => row.registration_lifecycle === 'deleted'))
      assert.deepEqual(errors, [])
      console.log(`${width}px: real endpoints + UI lifecycle, check-in/ID history, Finance NGN labels and unchanged NGN 4000 passed`)
      await page.unrouteAll({ behavior: 'ignoreErrors' }); await context.close()
    }
  } finally {
    for (const context of browser.contexts()) for (const page of context.pages()) { await page.unrouteAll({ behavior: 'ignoreErrors' }) }
    await browser.close()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
