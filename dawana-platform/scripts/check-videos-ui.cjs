/* Start local Vite on 127.0.0.1:5178. Every API and video-player request is mocked. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178'
const videos = [
  { id: 1, edition: { id: 1, name: 'Synthetic edition A' }, activities: [{ id: 1, name: 'Synthetic learning' }], caption: 'Synthetic recording A', alt_text: 'Synthetic thumbnail A', provider: 'youtube', featured: true },
  { id: 2, edition: { id: 2, name: 'Synthetic edition B' }, activities: [{ id: 2, name: 'Synthetic games' }], caption: 'Synthetic recording B', alt_text: 'Synthetic thumbnail B', provider: 'vimeo' },
  { id: 3, edition: { id: 1, name: 'Synthetic edition A' }, activities: [{ id: 2, name: 'Synthetic games' }], caption: 'Synthetic recording C', alt_text: 'Synthetic thumbnail C', provider: 'youtube' },
].map(video => ({ ...video, thumbnail_url: `/mock-video-thumbnail/${video.id}`, playback_url: `/api/v1/dic/videos/${video.id}/playback/` }))

;(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  try {
    const page = await browser.newPage()
    const errors = []
    let empty = false, unavailable = false, playbackCalls = 0, playerCalls = 0, mutations = 0
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/*', route => {
      const request = route.request(), url = new URL(request.url())
      if (url.origin !== base) {
        if (['www.youtube-nocookie.com', 'player.vimeo.com'].includes(url.hostname)) {
          playerCalls++
          return route.fulfill({ contentType: 'text/html', body: '<html><body><button aria-label="Synthetic player control">Play</button></body></html>' })
        }
        return route.abort()
      }
      if (request.method() !== 'GET') { mutations++; return route.abort() }
      if (url.pathname === '/api/v1/dic/videos/') return route.fulfill({ json: { videos: empty ? [] : videos } })
      if (/\/videos\/\d+\/playback\/$/.test(url.pathname)) {
        playbackCalls++
        if (unavailable) return route.fulfill({ status: 404, json: { detail: 'Unavailable' } })
        const id = Number(url.pathname.split('/')[5])
        return route.fulfill({ json: id === 2 ? { provider: 'vimeo', embed_url: 'https://player.vimeo.com/video/123456?dnt=1' } : { provider: 'youtube', embed_url: 'https://www.youtube-nocookie.com/embed/aaaaaaaaaaa?playsinline=1' } })
      }
      if (url.pathname.startsWith('/mock-video-thumbnail/')) return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64') })
      if (url.pathname.includes('/registration-options/')) return route.fulfill({ json: { name: 'Synthetic camp', camp_start_date: '2026-12-23', camp_end_date: '2027-01-01', registration_is_open: false, categories: [] } })
      if (url.pathname === '/api/v1/dic/memories/') return route.fulfill({ json: { photographs: [] } })
      if (url.pathname.startsWith('/api/')) return route.fulfill({ status: 404, json: {} })
      return route.continue()
    })
    await page.goto(base + '/dic')
    const opener = page.getByRole('button', { name: 'Play video: Synthetic recording A', exact: true })
    await opener.waitFor()
    assert.equal(await page.locator('.video-card').count(), 3)
    assert.equal(await page.locator('.video-card img[loading=lazy]').count(), 3)
    assert.equal(await page.locator('iframe').count(), 0)
    assert.equal(playbackCalls, 0)
    assert.equal(playerCalls, 0)
    await page.getByLabel('Video camp edition', { exact: true }).selectOption('1')
    await page.getByLabel('Video activity', { exact: true }).selectOption('2')
    assert.equal(await page.locator('.video-card').count(), 1)
    assert.match(await page.locator('.video-card').innerText(), /Synthetic recording C/)
    await page.getByLabel('Video camp edition', { exact: true }).selectOption('')
    await page.getByLabel('Video activity', { exact: true }).selectOption('')
    await opener.click()
    const viewer = page.getByRole('dialog')
    await viewer.locator('iframe').waitFor()
    assert.equal(await page.getByRole('button', { name: 'Close video viewer' }).evaluate(el => el === document.activeElement), true)
    assert.match(await viewer.locator('iframe').getAttribute('src'), /youtube-nocookie/)
    assert.equal(await viewer.locator('iframe').getAttribute('title'), 'Synthetic recording A')
    assert.ok(!(await viewer.locator('iframe').getAttribute('allow')).includes('autoplay'))
    await page.keyboard.press('Shift+Tab')
    assert.equal(await viewer.evaluate(el => el.contains(document.activeElement)), true)
    await page.keyboard.press('ArrowRight')
    await viewer.locator('iframe[src*="player.vimeo.com"]').waitFor()
    await page.keyboard.press('ArrowLeft')
    await viewer.locator('iframe[src*="youtube-nocookie"]').waitFor()
    await page.keyboard.press('Escape')
    assert.equal(await viewer.isVisible(), false)
    assert.equal(await page.locator('iframe').count(), 0)
    assert.equal(await opener.evaluate(el => el === document.activeElement), true)
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 })
      await page.locator('.dic-videos').scrollIntoViewIfNeeded()
      assert.equal(await page.locator('.dic-videos').evaluate(el => el.scrollWidth <= el.clientWidth), true, `gallery overflow ${width}`)
      await opener.click()
      await viewer.locator('iframe').waitFor()
      assert.equal(await viewer.evaluate(el => el.scrollWidth <= el.clientWidth), true)
      await page.getByRole('button', { name: 'Close video viewer' }).click()
    }
    await page.emulateMedia({ reducedMotion: 'reduce' })
    assert.ok(await page.locator('.video-card').first().evaluate(el => parseFloat(getComputedStyle(el).transitionDuration) <= .00001))
    await page.screenshot({ path: require('node:path').join(require('node:os').tmpdir(), 'dawana-videos-mobile.png'), fullPage: false })
    unavailable = true
    await opener.click()
    await viewer.getByRole('alert').waitFor()
    assert.equal(await viewer.locator('iframe').count(), 0)
    await page.getByRole('button', { name: 'Close video viewer' }).click()
    empty = true
    await page.reload()
    await page.getByText('The next story is on its way', { exact: true }).waitFor()
    assert.equal(await page.locator('.video-card').count(), 0)
    assert.equal(mutations, 0)
    assert.deepEqual(errors, [])
    console.log('PASS: edition/activity filters, lazy thumbnails, zero eager players, canonical YouTube/Vimeo playback, keyboard/focus/close, four viewport widths, reduced motion, withdrawn-video error, empty state; all external players mocked.')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
