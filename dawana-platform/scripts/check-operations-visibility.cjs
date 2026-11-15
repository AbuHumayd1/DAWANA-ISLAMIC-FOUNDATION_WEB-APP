/* Real browser + real synthetic Django API. Never targets production. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178', api = process.env.OWNER_TEST_API
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(api || '')) throw new Error('Disposable loopback API required')
const records = JSON.parse(process.env.OWNER_TEST_RECORDS)
;(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : {}) })
  try {
    for (const width of [390, 768, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 960 } })
      await context.addCookies([{ name: 'sessionid', value: process.env.OWNER_TEST_SESSION, url: base, httpOnly: true, sameSite: 'Lax' }])
      const page = await context.newPage(), errors = []
      page.setDefaultTimeout(20000)
      page.on('pageerror', error => errors.push(error.message))
      page.on('dialog', dialog => dialog.accept())
      let apiQueue = Promise.resolve()
      await page.route('**/*', async route => {
        const url = new URL(route.request().url())
        if (url.origin !== base) return route.abort()
        if (!url.pathname.startsWith('/api/')) return route.continue()
        const task = apiQueue.then(async () => {
          const original = route.request().headers()
          const cookies = (original.cookie || '').split(';').filter(value => !value.trim().startsWith('sessionid=')).filter(Boolean)
          const headers = { ...original, cookie: [...cookies, 'sessionid=' + process.env.OWNER_TEST_SESSION].join('; ') }
          const response = await route.fetch({ url: api + url.pathname + url.search, headers, timeout: 30000 })
          if (response.status() >= 400) console.log('API error', url.pathname, await response.text())
          return route.fulfill({ response })
        })
        apiQueue = task.catch(() => {})
        try { await task } catch (error) { console.error(error.message); await route.abort().catch(() => {}) }

      })
      const nav = () => page.getByRole('navigation', { name: 'Registration records', exact: true })
      const tab = view => nav().locator(`a${view === 'active' ? ':not([href*="archive="])' : `[href*="archive=${view}"]`}`)
      const row = record => page.locator('tbody tr').filter({ hasText: record.id.slice(0, 8) })
      const counts = async expected => {
        const values = await page.evaluate(async () => {
          const root = '/api/v1/dic/operations'
          const get = path => fetch(root + path).then(r => { if (!r.ok) throw new Error('API ' + r.status); return r.json() })
          return Promise.all([get('/campsite/'), get('/dashboard/'), get('/participants/'), get('/registrations/')])
        })
        assert.equal(values[0].metrics.registered_participants, expected)
        assert.equal(values[1].metrics.participants, expected)
        assert.equal(values[2].count, expected)
        assert.equal(values[3].count, expected === 3 ? 2 : 1)
      }
      await page.goto(base + '/dic/operations/registrations')
      await nav().waitFor()
      await counts(3)
      for (const record of records) {
        await row(record).getByRole('button', { name: 'Delete', exact: true }).click()
        await row(record).waitFor({ state: 'detached' })
        await counts(3 - record.participants)
        await tab('all').click(); await row(record).waitFor({ state: 'detached' })
        await tab('trash').click()
        await row(record).getByRole('button', { name: 'Restore', exact: true }).click()
        await row(record).waitFor({ state: 'detached' }); await counts(3)
        await tab('active').click()
        await row(record).getByRole('button', { name: 'Archive', exact: true }).click()
        await row(record).waitFor({ state: 'detached' }); await counts(3 - record.participants)
        await tab('all').click(); await row(record).waitFor()
        await tab('archived').click()
        assert.equal(await nav().locator('[aria-current="page"]').count(), 1)
        await row(record).getByRole('button', { name: 'Unarchive', exact: true }).click()
        await row(record).waitFor({ state: 'detached' }); await counts(3)
        await tab('active').click(); await row(record).waitFor()
      }
      assert.equal(await nav().getByRole('link').count(), 4)
      assert.ok(await nav().evaluate(el => el.scrollWidth <= el.clientWidth))
      await tab('active').focus()
      await page.keyboard.press('Tab')
      await page.keyboard.press('Shift+Tab')
      assert.equal(await tab('active').evaluate(el => getComputedStyle(el).outlineStyle), 'solid')
      await page.keyboard.press('Tab'); await page.keyboard.press('Enter')
      await page.waitForURL('**archive=all')
      await nav().locator('a[href*="archive=all"][aria-current="page"]').waitFor()
      assert.equal(await tab('all').getAttribute('aria-current'), 'page')
      await page.screenshot({ path: `../operations-tabs-${width}.png`, fullPage: true })
      await page.goto(base + '/dic/operations/participants')
      await page.getByRole('link', { name: 'Paid Participant A', exact: true }).waitFor()
      await page.getByRole('link', { name: 'Paid Participant B', exact: true }).waitFor()
      await page.getByRole('link', { name: 'Unpaid Participant', exact: true }).waitFor()
      assert.deepEqual(errors, [])
      console.log(`${width}px: real API counts, multi-participant Delete/Restore/Archive/Unarchive, lists and keyboard tabs passed`)
      await context.close()
    }
  } finally { for (const context of browser.contexts()) for (const page of context.pages()) await page.unrouteAll({ behavior: 'ignoreErrors' }); await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
