/* Local Vite on 127.0.0.1:5178; all APIs/external requests are intercepted.
   Run with node scripts/check-payment-return.cjs and an installed Playwright/Chrome.
   PLAYWRIGHT_MODULE_PATH can point to an existing installation. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178'
const a = '11111111-1111-4111-8111-111111111111'
const b = '22222222-2222-4222-8222-222222222222'
const references = { DICmockA: a, DICmockB: b }
const orders = {
  [a]: { order_id: a, edition_name: 'Synthetic browser edition', payment_status: 'paid', status: 'confirmed', currency: 'NGN', total_amount_ngn: '1000.00', participants: [{ name: 'Synthetic Participant A', category: 'Synthetic category' }] },
  [b]: { order_id: b, edition_name: 'Synthetic browser edition', payment_status: 'pending', status: 'submitted', attempt_status: 'pending', currency: 'NGN', total_amount_ngn: '1000.00', participants: [{ name: 'Synthetic Participant B', category: 'Synthetic category' }] },
}

;(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const grants = new Set()
    const errors = []
    let initializationCalls = 0, hold = true, outage = null
    const waiting = []
    async function intercept(route) {
      const request = route.request(), url = new URL(request.url())
      if (url.origin !== base) return route.abort()
      const json = (body, status = 200, headers = {}) => route.fulfill({ status, json: body, headers })
      if (url.pathname.endsWith('/auth/csrf/')) return json({ csrfToken: 'synthetic-csrf' })
      if (url.pathname.endsWith('/payment-return-grant/')) {
        assert.equal(request.headers().authorization, 'Bearer synthetic-order-proof')
        assert.equal(request.headers()['x-csrftoken'], 'synthetic-csrf')
        const id = url.pathname.split('/')[5]
        grants.add(id)
        return json({ ready: true }, 200, { 'Set-Cookie': 'dic_mock_session=synthetic-cookie; Path=/; HttpOnly; SameSite=Lax' })
      }
      if (url.pathname === '/api/v1/dic/payments/return/') {
        if (outage === 'network') return route.abort('failed')
        if (outage) return json({ detail: 'synthetic-private-provider-detail' }, outage)
        assert.equal(request.headers()['x-csrftoken'], 'synthetic-csrf')
        assert.equal(request.headers().authorization, undefined)
        if (!request.headers().cookie?.includes('dic_mock_session=synthetic-cookie')) return json({ detail: 'Secure return session unavailable.' }, 404)
        const lookup = request.postDataJSON()
        let id = lookup.order_id
        if (lookup.reference) {
          const found = references[lookup.reference]
          if (!found || (id && id !== found)) return json({ detail: 'Secure return session unavailable.' }, 404)
          id = found
        }
        if (!id) return json({ orders: [...grants].map((id) => orders[id]) })
        if (!grants.has(id)) return json({ detail: 'Secure return session unavailable.' }, 404)
        if (hold) await new Promise((resolve) => waiting.push(resolve))
        return json({ order: orders[id] })
      }
      if (url.pathname.includes('/payments/initialize/')) { initializationCalls += 1; return json({}, 500) }
      if (url.pathname.includes('/recovery/channels/')) return json({ channels: [{ id: 'email', available: false }] })
      if (url.pathname.startsWith('/api/')) return json({}, 404)
      return route.continue()
    }
    await context.route('**/*', intercept)
    context.on('page', (page) => page.on('pageerror', (error) => errors.push(error.message)))
    const original = await context.newPage()
    await original.goto(base)
    async function prepare(page, id) {
      await page.evaluate(async (id) => {
        const api = await import('/src/services/paymentReturnApi.js')
        await api.preparePaymentReturn(id, 'synthetic-order-proof')
      }, id)
    }
    await prepare(original, a)
    assert.ok((await context.cookies()).find((cookie) => cookie.name === 'dic_mock_session').httpOnly)
    assert.ok(!await original.evaluate(() => document.cookie.includes('dic_mock_session')))
    await original.evaluate(() => sessionStorage.setItem('original-tab-marker', 'draft'))
    await original.goto(base + '/dic/register/payment-return?reference=DICmockA&trxref=DICmockA')
    await original.getByRole('heading', { name: 'Checking your payment' }).waitFor()
    await original.reload()
    await original.getByRole('heading', { name: 'Checking your payment' }).waitFor()
    hold = false
    waiting.splice(0).forEach((resolve) => resolve())
    await original.getByRole('heading', { name: 'DIC registration confirmed' }).waitFor()
    await original.waitForURL(base + '/dic/register/confirmation/' + a)
    await original.reload()
    await original.getByRole('heading', { name: 'DIC registration confirmed' }).waitFor()
    assert.match(await original.locator('.confirmation-box').innerText(), /1,000\.00/)
    for (const failure of [503, 'network', 403]) {
      outage = failure
      await original.reload()
      await original.getByRole('heading', { name: failure === 403 ? 'Secure access required' : 'Payment status temporarily unavailable' }).waitFor()
      assert.equal(await original.getByText('Synthetic Participant A', { exact: true }).count(), 0)
      assert.equal(await original.getByText(/synthetic-private-provider-detail/).count(), 0)
      assert.equal(await original.getByRole('link', { name: 'Recover existing registration' }).count(), 0)
      outage = null
      await original.getByRole('button', { name: 'Retry payment status check' }).click()
      await original.getByRole('heading', { name: 'DIC registration confirmed' }).waitFor()
    }
    await prepare(original, b)
    const callback = await context.newPage()
    await callback.goto(base + '/dic/register/payment-return?reference=DICmockB&payment_status=paid')
    await callback.getByRole('heading', { name: 'Payment awaiting confirmation' }).waitFor()
    assert.equal(await callback.evaluate(() => sessionStorage.getItem('original-tab-marker')), null)
    orders[b].attempt_status = 'reconcile'
    await callback.getByRole('button', { name: 'Check existing payment again' }).click()
    await callback.getByRole('heading', { name: 'Payment needs review' }).waitFor()
    orders[b].attempt_status = 'failed'; orders[b].payment_status = 'failed'
    await callback.getByRole('button', { name: 'Check existing payment again' }).click()
    await callback.getByRole('heading', { name: 'Payment not completed' }).waitFor()
    orders[b].payment_status = 'paid'; orders[b].status = 'confirmed'
    await callback.getByRole('button', { name: 'Check existing payment again' }).click()
    await callback.getByRole('heading', { name: 'DIC registration confirmed' }).waitFor()
    await callback.waitForURL(base + '/dic/register/confirmation/' + b)
    await callback.reload()
    await callback.getByText('Synthetic Participant B', { exact: true }).waitFor()
    for (const width of [1440, 768, 390, 320]) {
      await callback.setViewportSize({ width, height: 900 })
      for (const theme of ['light', 'dark']) {
        await callback.evaluate((theme) => { document.documentElement.dataset.theme = theme }, theme)
        assert.ok(await callback.locator('.confirmation-box').evaluate((el) => el.scrollWidth <= innerWidth && el.getBoundingClientRect().right <= innerWidth), `confirmation overflow at ${width}/${theme}`)
      }
    }
    if (process.env.DIC_UI_SCREENSHOTS) await callback.locator('.confirmation-box').screenshot({ path: '.tmp-payment-return.png' })
    await callback.goto(base + '/dic/register/payment-return')
    await callback.getByRole('heading', { name: 'Choose your registration' }).waitFor()
    await callback.locator('.dic-return-orders li').filter({ hasText: a }).getByRole('button').click()
    await callback.getByText('Synthetic Participant A', { exact: true }).waitFor()
    await callback.goto(base + '/dic/register/payment-return?reference=DICforged')
    await callback.getByRole('heading', { name: 'Recover your registration' }).waitFor()
    assert.ok(!await callback.getByText('Synthetic Participant A', { exact: true }).count())
    await context.clearCookies()
    await callback.goto(base + '/dic/register/confirmation/' + b)
    await callback.getByText(/Automated contact recovery is currently unavailable/).waitFor()
    assert.ok(!await callback.getByText('Synthetic Participant B', { exact: true }).count())
    await callback.reload()
    await callback.getByRole('link', { name: 'Recover existing registration' }).waitFor()
    assert.equal(initializationCalls, 0)
    assert.deepEqual(errors, [])
    console.log('PASS: same/new-tab return, shared HttpOnly cookie, no draft/bearer dependency, reload before/after confirmation, multi-order selection, forged/expired session denial, pending/failed/paid views, unavailable OTP guidance, four widths and both themes. No initialization or live API calls.')
  } finally { await browser.close() }
})().catch((error) => { console.error(error); process.exitCode = 1 })
