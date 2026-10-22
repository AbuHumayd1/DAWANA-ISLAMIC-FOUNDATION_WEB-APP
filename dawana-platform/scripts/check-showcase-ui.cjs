/* Local Vite on 127.0.0.1:5178; all APIs/images use synthetic, intercepted data. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178'
const person = { name: 'Synthetic Lecturer A', designation: 'Synthetic designation', biography: 'Synthetic biography for testing only.', alt_text: 'Synthetic green portrait', image_url: '/mock-showcase/portrait', topic: 'Synthetic approved topic', edition: { id: 1, name: 'Synthetic edition 2026' } }
const content = {
  upcoming: [{ ...person, id: 1, confirmed: true, featured: true }, { ...person, id: 2, name: 'Synthetic Lecturer B', confirmed: false }],
  previous: [{ ...person, id: 3, confirmed: true, edition: { id: 2, name: 'Synthetic edition A' } }, { ...person, id: 4, confirmed: false, topic: 'MUST NOT APPEAR', edition: { id: 3, name: 'Synthetic edition B' } }],
  activities: [{ id: 1, title: 'Synthetic approved activity', description: 'Synthetic description; no real schedule.', category: 'Synthetic category', featured: true, image_url: '/mock-showcase/activity', alt_text: 'Synthetic illustration' }, { id: 2, title: 'Synthetic text-only activity', description: 'Synthetic text description.', category: 'Synthetic category', image_url: null }],
}

;(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const errors = []
    let mode = 'content', mutations = 0
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/*', route => {
      const request = route.request(), url = new URL(request.url())
      if (url.origin !== base) return route.abort()
      if (request.method() !== 'GET') { mutations++; return route.abort() }
      if (url.pathname === '/api/v1/dic/showcase/') return mode === 'error' ? route.fulfill({ status: 503, json: {} }) : route.fulfill({ json: mode === 'empty' ? { upcoming: [], previous: [], activities: [] } : content })
      if (url.pathname === '/api/v1/dic/memories/') return route.fulfill({ json: { photographs: [] } })
      if (url.pathname === '/api/v1/dic/videos/') return route.fulfill({ json: { videos: [] } })
      if (url.pathname.includes('/registration-options/')) return route.fulfill({ json: { name: 'Synthetic camp', camp_start_date: '2026-12-23', camp_end_date: '2027-01-01', registration_is_open: false, categories: [] } })
      if (url.pathname.startsWith('/mock-showcase/')) return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64') })
      if (url.pathname.startsWith('/api/')) return route.fulfill({ status: 404, json: {} })
      return route.continue()
    })
    await page.goto(base + '/dic')
    await page.getByRole('heading', { name: 'Upcoming DIC 2026 Lecturers', exact: true }).waitFor()
    await page.locator('.showcase-upcoming .showcase-lecturer').last().waitFor()
    assert.equal(await page.locator('.showcase-upcoming .showcase-lecturer').count(), 2)
    assert.match(await page.locator('.showcase-upcoming .showcase-lecturer').first().innerText(), /Participation confirmed/)
    assert.match(await page.locator('.showcase-upcoming .showcase-lecturer').last().innerText(), /Participation awaiting confirmation/)
    assert.equal(await page.getByText('MUST NOT APPEAR', { exact: true }).count(), 0)
    assert.equal(await page.locator('.showcase-activity').count(), 2)
    assert.equal(await page.locator('.showcase-activity img').count(), 1)
    assert.equal(await page.locator('.dic-showcase img:not([alt])').count(), 0)
    assert.equal(await page.locator('.dic-showcase img:not([loading=lazy])').count(), 0)
    const filter = page.getByRole('combobox', { name: 'Past lecturer edition', exact: true })
    await filter.focus()
    assert.equal(await filter.evaluate(el => el === document.activeElement), true)
    await filter.selectOption('2')
    assert.equal(await page.locator('.showcase-previous .showcase-lecturer').count(), 1)
    assert.match(await page.locator('.showcase-previous .showcase-lecturer').innerText(), /Synthetic edition A/)
    await filter.selectOption('')
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 })
      for (const section of ['.showcase-upcoming', '.showcase-previous', '.showcase-activities']) {
        await page.locator(section).scrollIntoViewIfNeeded()
        assert.equal(await page.locator(section).evaluate(el => el.scrollWidth <= el.clientWidth && [...el.querySelectorAll('article, select')].every(child => child.getBoundingClientRect().right <= innerWidth + 1 && child.getBoundingClientRect().left >= 0)), true, `${section} overflow at ${width}`)
      }
    }
    await page.emulateMedia({ reducedMotion: 'reduce' })
    assert.equal(await page.locator('.showcase-activity').first().evaluate(el => getComputedStyle(el).transform), 'none')
    assert.ok(await page.locator('.showcase-activity').first().evaluate(el => parseFloat(getComputedStyle(el).transitionDuration) <= .00001))
    await page.screenshot({ path: require('node:path').join(require('node:os').tmpdir(), 'dawana-showcase-mobile.png') })
    mode = 'empty'
    await page.reload()
    await page.getByText('Meet the lecturers when details are approved', { exact: true }).waitFor()
    await page.getByText('The programme is being prepared', { exact: true }).waitFor()
    assert.equal(await page.locator('.dic-showcase article').count(), 0)
    mode = 'error'
    await page.reload()
    await page.locator('.showcase-upcoming').getByText('Camp content is temporarily unavailable. Please visit again later.', { exact: true }).waitFor()
    assert.equal(mutations, 0)
    assert.deepEqual(errors, [])
    console.log('PASS: explicit lecturer confirmation, private/unverified topics absent, edition filters, accessible/lazy images, text-only activities, keyboard filter, four widths, reduced motion, empty/error states; synthetic traffic only.')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
