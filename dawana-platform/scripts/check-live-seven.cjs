/* Synthetic local browser regression. No provider or production requests. */
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = 'http://127.0.0.1:5178'
const id = '12345678-abcd-4321-abcd-123456789012'
const person = { id, name: 'Synthetic Camper', registration_item_id: 1, participant_number: 'SYNTHETIC', category: 'Adult',
  eligibility: { eligible: true, code: 'verified_paid' }, issue: { status: 'current', version: 1 } }
const expires_at = () => new Date(Date.now() + 600000).toISOString()
;(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  try {
    const context = await browser.newContext()
    let signedIn = false, hold = false, release, failLookup = false, logoutRequests = 0
    const failedLogout = [], errors = []
    await context.route('**/*', async route => {
      const url = new URL(route.request().url())
      if (url.origin !== base) return route.abort()
      if (!url.pathname.startsWith('/api/')) return route.continue()
      const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
      if (url.pathname.endsWith('/csrf/')) return json({ csrfToken: 'synthetic' })
      if (url.pathname.endsWith('/auth/capabilities/')) return json({ accounts: { enabled: true }, session: { remember_seconds: 28800 } })
      if (url.pathname.endsWith('/auth/password/login/')) { signedIn = true; return json({ authenticated: true, expires_at: expires_at() }) }
      if (url.pathname.endsWith('/auth/logout/')) {
        logoutRequests++; await new Promise(resolve => setTimeout(resolve, 250)); signedIn = false; return json({})
      }
      if (url.pathname.endsWith('/enrollments/')) {
        const authorized = signedIn
        if (hold) await new Promise(resolve => { release = resolve })
        if (failLookup) return json({ detail: 'Lookup temporarily unavailable.' }, 503)
        return json(authorized ? { authenticated: true, expires_at: expires_at(), orders: [{ reference: 'synthetic', edition: 'Synthetic Camp', participants: [person] }] } : { authenticated: false })
      }
      if (url.pathname.endsWith('/id/')) return json({ id, name: person.name, participant_number: person.participant_number })
      return json({ ready: false, standings: [], contributions: [], results: [] })
    })
    const page = await context.newPage()
    page.on('pageerror', error => errors.push(error.message))
    page.on('requestfailed', request => { if (request.url().endsWith('/auth/logout/')) failedLogout.push(request.failure()) })
    await page.goto(base + '/dic/participant?view=me')
    await page.getByRole('button', { name: 'Sign In', exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Retry secure access', exact: true }).count(), 0)
    await page.getByLabel('Username', { exact: true }).fill('synthetic-owner')
    await page.getByLabel('Password', { exact: true }).fill('synthetic-password')
    hold = true
    await page.getByRole('button', { name: 'Sign In', exact: true }).click()
    await page.getByText('Loading authorized campers…', { exact: true }).waitFor()
    assert.equal(await page.getByRole('heading', { name: 'No campers linked yet' }).count(), 0)
    assert.ok(release)
    hold = false; release()
    await page.locator('.cp-header').waitFor()

    const other = await context.newPage()
    await other.goto(base + '/dic/participant?view=me')
    await other.locator('.cp-header').waitFor()
    await page.locator('.cw-account-drawer > summary').click()
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await page.getByText('Signed out.', { exact: true }).waitFor()
    await other.getByRole('button', { name: 'Sign In', exact: true }).waitFor()
    assert.equal(logoutRequests, 1)
    assert.deepEqual(failedLogout, [])
    await page.reload()
    await page.getByRole('button', { name: 'Sign In', exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Retry server sign-out' }).count(), 0)
    assert.equal(await page.getByText('Could not confirm your participant session. Please sign in again.', { exact: true }).count(), 0)

    await page.getByLabel('Username', { exact: true }).fill('synthetic-owner')
    await page.getByLabel('Password', { exact: true }).fill('synthetic-password')
    failLookup = true
    await page.getByRole('button', { name: 'Sign In', exact: true }).click()
    await page.getByText('Lookup temporarily unavailable.', { exact: true }).waitFor()
    assert.equal(await page.getByRole('heading', { name: 'No campers linked yet' }).count(), 0)
    failLookup = false
    await page.getByRole('button', { name: 'Retry secure access', exact: true }).click()
    await page.locator('.cp-header').waitFor()

    // An older positive response cannot republish access after another tab logs out.
    await other.getByLabel('Username', { exact: true }).fill('synthetic-owner')
    await other.getByLabel('Password', { exact: true }).fill('synthetic-password')
    await other.getByRole('button', { name: 'Sign In', exact: true }).click()
    await other.locator('.cp-header').waitFor()
    hold = true
    const navigation = page.reload()
    await page.getByRole('heading', { name: 'Opening your Camper Portal' }).waitFor()
    await other.locator('.cw-account-drawer > summary').click()
    await other.getByRole('button', { name: 'Sign out', exact: true }).click()
    await other.getByText('Signed out.', { exact: true }).waitFor()
    hold = false; release()
    await navigation
    await page.getByRole('button', { name: 'Sign In', exact: true }).waitFor()
    assert.equal(await page.locator('.cp-header').count(), 0)
    assert.deepEqual(errors, [])
    console.log('PASS: signed-out startup, delayed lookup, lookup failure/retry, actual logout, cross-tab clearing, stale response rejection')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
