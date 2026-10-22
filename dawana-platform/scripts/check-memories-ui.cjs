/* All content and API traffic is synthetic. Start Vite on 127.0.0.1:5178. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178'
const photos = [
  { id: 1, edition: { id: 1, name: 'Synthetic past edition A' }, activities: [{ id: 1, name: 'Synthetic learning' }], caption: 'Synthetic memory A', alt_text: 'Synthetic green photograph A', image_url: '/mock-photo/1' },
  { id: 2, edition: { id: 2, name: 'Synthetic past edition B' }, activities: [{ id: 2, name: 'Synthetic recreation' }], caption: 'Synthetic memory B', alt_text: 'Synthetic green photograph B', image_url: '/mock-photo/2' },
  { id: 3, edition: { id: 1, name: 'Synthetic past edition A' }, activities: [{ id: 2, name: 'Synthetic recreation' }], caption: 'Synthetic memory C', alt_text: 'Synthetic green photograph C', image_url: '/mock-photo/3' },
]

;(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  try {
    const page = await browser.newPage()
    const errors = []
    let empty = false
    let mutations = 0
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/*', route => {
      const request = route.request()
      const url = new URL(request.url())
      if (url.origin !== base) return route.abort()
      if (request.method() !== 'GET') { mutations++; return route.abort() }
      if (url.pathname === '/api/v1/dic/memories/') return route.fulfill({ json: { photographs: empty ? [] : photos } })
      if (url.pathname.includes('/registration-options/')) return route.fulfill({ json: { name: 'Synthetic edition', camp_start_date: '2026-12-23', camp_end_date: '2027-01-01', registration_is_open: false, categories: [] } })
      if (url.pathname.startsWith('/mock-photo/')) return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64') })
      if (url.pathname.startsWith('/api/')) return route.fulfill({ status: 404, json: {} })
      return route.continue()
    })
    await page.goto(base + '/dic')
    await page.getByRole('button', { name: 'View photograph: Synthetic memory A', exact: true }).waitFor()
    assert.equal(await page.locator('.memory-card').count(), 3)
    assert.equal(await page.locator('.memory-card img[loading=lazy]').count(), 3)
    await page.getByLabel('Camp edition', { exact: true }).selectOption('1')
    assert.equal(await page.locator('.memory-card').count(), 2)
    await page.getByLabel('Activity', { exact: true }).selectOption('2')
    assert.equal(await page.locator('.memory-card').count(), 1)
    assert.match(await page.locator('.memory-card').innerText(), /Synthetic memory C/)
    await page.getByLabel('Camp edition', { exact: true }).selectOption('')
    await page.getByLabel('Activity', { exact: true }).selectOption('')
    const opener = page.getByRole('button', { name: 'View photograph: Synthetic memory A', exact: true })
    await opener.focus() // Focus pauses the decorative sway before pointer interaction.
    await opener.click()
    const viewer = page.getByRole('dialog', { name: 'Camp photograph viewer' })
    await viewer.waitFor()
    assert.equal(await page.getByRole('button', { name: 'Close photograph viewer' }).evaluate(el => el === document.activeElement), true)
    await page.keyboard.press('ArrowRight')
    assert.equal(await viewer.locator('img').getAttribute('alt'), 'Synthetic green photograph B')
    await page.keyboard.press('ArrowLeft')
    assert.equal(await viewer.locator('img').getAttribute('alt'), 'Synthetic green photograph A')
    await page.keyboard.press('Shift+Tab')
    assert.equal(await viewer.evaluate(el => el.contains(document.activeElement)), true)
    await page.keyboard.press('Escape')
    assert.equal(await viewer.isVisible(), false)
    assert.equal(await opener.evaluate(el => el === document.activeElement), true)
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 })
      await page.locator('.dic-memories').scrollIntoViewIfNeeded()
      assert.equal(await page.locator('.dic-memories').evaluate(el => el.scrollWidth <= el.clientWidth && [...el.querySelectorAll('.memory-open, select')].every(child => child.getBoundingClientRect().left >= 0 && child.getBoundingClientRect().right <= innerWidth)), true, `gallery overflow at ${width}`)
      await opener.focus() // Focus pauses the decorative sway before pointer interaction.
      await opener.click()
      assert.equal(await viewer.evaluate(el => el.scrollWidth <= el.clientWidth), true)
      await page.getByRole('button', { name: 'Close photograph viewer' }).click()
    }
    await page.emulateMedia({ reducedMotion: 'reduce' })
    assert.equal(await page.locator('.memory-card').first().evaluate(el => getComputedStyle(el).animationName), 'none')
    assert.equal(await page.locator('.memory-card').first().evaluate(el => getComputedStyle(el).transform), 'none')
    await page.screenshot({ path: require('node:path').join(require('node:os').tmpdir(), 'dawana-memories-mobile.png'), fullPage: false })
    empty = true
    await page.reload()
    await page.getByText('Our scrapbook is being prepared', { exact: true }).waitFor()
    assert.equal(await page.locator('.memory-card').count(), 0)
    assert.equal(mutations, 0)
    assert.deepEqual(errors, [])
    console.log('PASS: gallery filters, lazy images, keyboard viewer/focus restoration, focus containment, four mobile/desktop widths, reduced motion, honest empty state; no mutations or external traffic.')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
