/* Local browser regression: every API and external request is intercepted. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178'

;(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  try {
    for (const mode of ['create', 'existing']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
      let submissions = 0, initializations = 0
      const errors = []
      page.on('pageerror', e => errors.push(e.message))
      await page.route('**/*', async route => {
        const url = new URL(route.request().url())
        if (url.href === 'https://checkout.paystack.com/synthetic') return route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>Synthetic checkout intercepted locally</h1>' })
        if (url.origin !== base) return route.abort()
        if (!url.pathname.startsWith('/api/')) return route.continue()
        const json = body => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
        if (url.pathname.endsWith('/auth/csrf/')) return json({ csrfToken: 'synthetic-csrf' })
        if (url.pathname.endsWith('/registration-options/')) return json({ name: 'Synthetic Camp', registration_is_open: true,
          camp_start_date: '2027-01-01', camp_end_date: '2027-01-07', categories: [{ id: 1, name: 'Synthetic Adult', minimum_age: 18, maximum_age: null, current_fee_ngn: '4000.00', regular_fee_ngn: '4000.00', current_price_type: 'regular' }] })
        if (url.pathname.endsWith('/orders/')) {
          submissions++
          const payload = route.request().postDataJSON()
          assert.equal(payload.portal_account.mode, mode)
          assert.equal(payload.portal_account.username, 'parent name')
          assert.equal(payload.portal_account.password, 'x')
          assert.equal(payload.portal_account.password_confirmation, mode === 'create' ? 'x' : undefined)
          await new Promise(resolve => setTimeout(resolve, 150))
          return json({ order_id: '11111111-1111-4111-8111-111111111111', access_token: 'synthetic-token', payment_status: 'pending', total_amount_ngn: '4000.00', items: [{ category_name: 'Synthetic Adult', fee_ngn: '4000.00', price_type: 'regular' }] })
        }
        if (url.pathname.endsWith('/payment-return-grant/')) return json({ ready: true })
        if (url.pathname.endsWith('/payments/initialize/')) {
          initializations++
          return json({ authorization_url: 'https://checkout.paystack.com/synthetic', payment_reference: 'synthetic-ref', payment_status: 'pending' })
        }
        return json({ channels: [] })
      })
      await page.goto(base + '/dic/register')
      await page.locator('#fullName').fill('Synthetic Participant')
      await page.locator('#address').fill('Synthetic address')
      await page.locator('#phone').fill('08000000000')
      await page.locator('#email').fill('synthetic@example.test')
      async function choose(label, text) {
        const box = page.getByRole('combobox', { name: label })
        await box.focus(); await box.press('Home')
        await box.press(text); await box.press('Enter')
      }
      await choose(/Age and date-of-birth/, 'a')
      await page.locator('#dob').fill('1990-01-01')
      await page.locator('input[name=sex][value=Male]').check()
      await choose(/Academic Status/, 't')
      await choose(/Occupation/, 'b')
      await choose(/Marital Status/, 's')
      await page.locator('input[name=categoryId][value="1"]').check()
      await page.getByRole('button', { name: /Continue to summary/ }).click()
      await page.getByRole('button', { name: /Continue to checkout/ }).click()
      await page.getByRole('textbox', { name: 'Primary camper or guardian name', exact: true }).fill('Synthetic Parent')
      await page.getByRole('textbox', { name: 'Booking email', exact: true }).fill('synthetic@example.test')
      await page.getByRole('combobox', { name: 'Account option' }).selectOption(mode)
      await page.getByRole('textbox', { name: 'Username', exact: true }).fill('Parent Name')
      await page.getByLabel(mode === 'create' ? 'Choose password' : 'Existing password', { exact: true }).fill('x')
      if (mode === 'create') await page.getByLabel('Confirm password', { exact: true }).fill('x')
      await page.getByRole('button', { name: 'Pay Now', exact: true }).click()
      await page.getByRole('heading', { name: 'Synthetic checkout intercepted locally' }).waitFor()
      assert.equal(submissions, 1); assert.equal(initializations, 1)
      assert.deepEqual(errors, [])
      await page.close()
    }
    for (const expired of [false, true]) {
      const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
      let recoveries = 0, initializations = 0
      const errors = []
      page.on('pageerror', e => errors.push(e.message))
      await page.route('**/*', async route => {
        const url = new URL(route.request().url())
        if (url.origin !== base) return route.abort()
        if (!url.pathname.startsWith('/api/')) return route.continue()
        const json = body => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
        if (url.pathname.endsWith('/auth/csrf/')) return json({ csrfToken: 'synthetic-csrf' })
        if (url.pathname.endsWith('/recovery/channels/')) return json({ channels: [] })
        if (url.pathname.endsWith('/auth/orders/recover/')) {
          recoveries++
          const payload = route.request().postDataJSON()
          assert.equal(payload.password, 'x')
          await new Promise(resolve => setTimeout(resolve, 200))
          return json({ orders: [{ access_token: 'synthetic-memory-only', order: {
            order_id: '11111111-1111-4111-8111-111111111111', edition_name: 'Synthetic Camp', participant_count: 1,
            payment_status: 'pending', total_amount_ngn: '4000.00', items: [],
            lifecycle: { enforced: true, expired, expires_at: expired ? '2000-01-01T00:00:00Z' : '2099-01-01T00:00:00Z' },
            payment_attempts: []
          } }] })
        }
        if (url.pathname.endsWith('/payment-return-grant/')) return json({ ready: true })
        if (url.pathname.endsWith('/payments/initialize/')) {
          initializations++
          return json({ authorization_url: 'https://checkout.paystack.com/synthetic', payment_reference: 'synthetic-ref', payment_status: 'pending' })
        }
        return json({ categories: [], registration_is_open: false })
      })
      await page.goto(base + '/dic/register/recover')
      const panel = page.getByRole('region', { name: 'Recover with participant account' })
      await panel.getByRole('textbox', { name: 'Username', exact: true }).fill('Parent Name')
      await panel.getByLabel('Password', { exact: true }).fill('x')
      await panel.getByRole('button', { name: 'Find my unpaid bookings' }).click()
      assert.equal(await panel.getByRole('button', { name: 'Finding bookings…' }).isDisabled(), true)
      await panel.getByRole('button', { name: 'Open booking status' }).click()
      assert.equal(recoveries, 1)
      const text = await page.locator('body').innerText()
      if (expired) {
        assert.match(text, /expired after 24 hours/)
        assert.equal(await page.getByRole('button', { name: /Continue to payment/ }).count(), 0)
        assert.equal(initializations, 0)
      } else {
        await page.getByRole('button', { name: /Continue to payment/ }).click()
        await page.getByRole('link', { name: /Open secure payment checkout/ }).waitFor()
        assert.equal(initializations, 1)
      }
      const stored = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))
      assert.doesNotMatch(stored, /synthetic-memory-only|Parent Name/)
      assert.deepEqual(errors, [])
      await page.screenshot({ path: `../output/phase-a/recovery-${expired ? 'expired' : 'pending'}-mobile.png`, fullPage: true })
      await page.close()
    }
    console.log('PASS: create/reuse registration, pending/expired account recovery, one-character password, duplicate-submit guard, checkout initialization, no credential persistence, mobile rendering.')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
