/* Local browser checks. All API/provider traffic is synthetic and intercepted. */
const assert = require('node:assert/strict')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178'
const id = '12345678-abcd-4321-abcd-123456789012'
const person = { id, name: 'Synthetic Camper', registration_item_id: 1, participant_number: 'SYNTHETIC-01',
  eligibility: { eligible: true, code: 'verified_paid' }, issue: { status: 'current', version: 1 }, category: 'Adult' }
const card = { id, name: person.name, participant_number: person.participant_number }
;(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  try {
    for (const width of [390, 900, 1440]) {
      let signedOut = false, empty = false, fail = false, startup = 0, probes = 0
      const page = await browser.newPage({ viewport: { width, height: 1000 } })
      const errors = []
      page.on('pageerror', e => errors.push(e.message))
      await page.route('**/*', async route => {
        const url = new URL(route.request().url())
        if (url.origin !== base) return route.abort()
        if (!url.pathname.startsWith('/api/')) return route.continue()
        const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
        if (url.pathname.endsWith('/csrf/')) return json({ csrfToken: 'synthetic' })
        if (url.pathname.endsWith('/auth/logout/')) { signedOut = true; return json({}) }
        if (url.pathname.includes('/participant/')) {
          if (url.pathname.endsWith('/auth/me/')) { probes++; return json({}, 403) }
          if (url.pathname.endsWith('/auth/capabilities/')) return json({ accounts: { enabled: true }, session: { remember_seconds: 28800 } })
          if (url.pathname.endsWith('/enrollments/')) {
            startup++
            await new Promise(resolve => setTimeout(resolve, 250))
            if (fail) return json({ detail: 'The participant service is unavailable. Please retry.' }, 503)
            return signedOut ? json({ detail: 'Please sign in.' }, 403) : json({ authenticated: true, expires_at: new Date(Date.now() + 600000).toISOString(), orders: empty ? [] : [
              { reference: 'synthetic-booking', edition: 'Synthetic Camp', participants: [person], status: 'confirmed', payment_status: 'paid' },
            ] })
          }
          if (url.pathname.endsWith('/id/')) return json(card)
          if (url.pathname.endsWith('/card/')) return route.fulfill({ contentType: 'text/html', body: '<h1>Protected synthetic issued ID</h1>' })
          return json({ ready: false, standings: [], contributions: [], count: 0, results: [] })
        }
        if (url.pathname.endsWith('/auth/me/')) return json({ display_name: 'Synthetic Staff', role: 'System Administrator', can_access_django_admin: true,
          can_access_campsite: true, permissions: { ids: true, manage_ids: true, registrations: true, participants: true, houses: true } })
        if (url.pathname.endsWith('/id-printing/')) return json({ results: [{ ...person, house: 'Synthetic House', version: 1 }], history: [] })
        if (url.pathname.endsWith('/enrollments/')) return json({ results: [person], registration_candidates: [], count: 1, next: null, previous: null })
        if (url.pathname.endsWith('/id/')) return json(card)
        return json({})
      })
      await page.goto(base + '/dic/participant?view=digital-id')
      await page.getByRole('heading', { name: 'Opening your Camper Portal' }).waitFor()
      await page.getByRole('button', { name: 'Open my Digital ID' }).click()
      await page.getByRole('link', { name: 'Preview PVC Card', exact: true }).waitFor()
      assert.equal(probes, 0)
      assert.equal(startup, 1)
      await page.getByRole('link', { name: 'Preview PVC Card', exact: true }).click()
      await page.getByRole('heading', { name: 'Protected synthetic issued ID' }).waitFor()
      // Return to the actual app and exercise a complete sign-out.
      await page.goto(base + '/dic/participant?view=me')
      await page.locator('.cw-account-drawer > summary').click()
      await page.getByRole('button', { name: 'Sign out', exact: true }).click()
      await page.getByRole('button', { name: 'Sign In', exact: true }).waitFor()
      assert.equal(await page.getByRole('button', { name: 'Retry server sign-out' }).count(), 0)
      const looseZero = await page.locator('section.participant-portal').evaluate(node => [...node.childNodes].some(child => child.nodeType === Node.TEXT_NODE && child.textContent.trim() === '0'))
      assert.equal(looseZero, false)
      await page.reload()
      await page.getByRole('button', { name: 'Sign In', exact: true }).waitFor()
      assert.equal(await page.getByRole('button', { name: 'Retry server sign-out' }).count(), 0)

      signedOut = false; empty = true
      await page.evaluate(() => localStorage.removeItem('dawana.participant.session-closed.v1'))
      await page.reload()
      await page.getByRole('heading', { name: 'No campers linked yet' }).waitFor()
      assert.ok(await page.getByRole('link', { name: 'Recover booking', exact: true }).isVisible())
      fail = true
      await page.reload()
      await page.getByRole('button', { name: 'Retry secure access', exact: true }).waitFor()
      empty = false; fail = false
      await page.getByRole('button', { name: 'Retry secure access', exact: true }).click()
      await page.locator('.cp-header').waitFor()
      await page.goto(base + '/dic/operations/participant-ids')
      await page.getByRole('button', { name: 'View / print current ID' }).click()
      const preview = page.getByRole('link', { name: 'Preview PVC Card', exact: true })
      await preview.waitFor()
      const appearance = await preview.evaluate(node => ({ height: node.getBoundingClientRect().height, display: getComputedStyle(node).display, background: getComputedStyle(node).backgroundColor }))
      assert.ok(appearance.height >= 44, JSON.stringify(appearance))
      assert.equal(appearance.display, 'flex')
      assert.notEqual(appearance.background, 'rgba(0, 0, 0, 0)')
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
      await page.screenshot({ path: path.resolve('../output/post-deployment/operations-id-' + width + '.png'), fullPage: true })
      const toggle = page.getByRole('button', { name: /navigation/ })
      if (await toggle.getAttribute('aria-expanded') === 'true') await toggle.click()
      assert.equal(await page.locator('#ops-sidebar').isVisible(), false)
      await toggle.click()
      assert.equal(await page.locator('#ops-sidebar').isVisible(), true)
      await page.goto(base + '/dic/operations/id-printing')
      await page.getByRole('heading', { name: 'ID Card Printing' }).waitFor()
      await page.getByText('SYNTHETIC-01', { exact: true }).waitFor()
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
      await page.screenshot({ path: path.resolve('../output/post-deployment/printing-' + width + '.png'), fullPage: true })
      await page.goto(base + '/faq')
      await page.locator('.footer').waitFor()
      assert.ok(await page.locator('.footer').evaluate(node => node.scrollWidth <= node.clientWidth + 1))
      await page.locator('.footer').screenshot({ path: path.resolve('../output/post-deployment/footer-' + width + '.png') })
      assert.deepEqual(errors, [])
      await page.close()
      console.log('Passed participant button/card, clean logout, ID styles, sidebar and printing at', width)
    }
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
