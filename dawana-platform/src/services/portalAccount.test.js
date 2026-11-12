import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import fs from 'node:fs'
import { googleAuthorizationUrl, oauthReturn } from './portalAccount.js'

let server, components
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  components = await server.ssrLoadModule('/src/components/dic/PortalAccountAccess.jsx')
})
after(async () => { await server?.close() })
const render = (name, props) => renderToStaticMarkup(createElement(components[name], props))

test('Google redirect accepts only the fixed provider and code/PKCE flow', () => {
  const valid = 'https://accounts.google.com/o/oauth2/v2/auth?response_type=code&code_challenge_method=S256'
  assert.equal(googleAuthorizationUrl(valid), valid)
  for (const value of ['https://evil.invalid/', valid.replace('accounts.google.com', 'accounts.google.com.evil.invalid'), valid.replace('response_type=code', 'response_type=token'), valid.replace('S256', 'plain'), valid+'#token=secret', '/dic/participant']) assert.throws(() => googleAuthorizationUrl(value))
})
test('callback fragments are hints rather than authenticated profiles', () => {
  assert.equal(oauthReturn('#signin=complete'), true)
  assert.equal(oauthReturn('#signin=failed'), true)
  for (const value of ['#paid=true', '#token=secret', '?signin=complete', null]) assert.equal(oauthReturn(value), false)
  const source = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
  assert.match(source, /oauthReturned\) read\(ticket, '\/auth\/me\/'/)
  assert.match(source, /window\.history\.replaceState/)
})
test('password setup remains gated with OTP recovery available and Google hidden', () => {
  const html = render('PortalCredentialLogin', { recoveryAvailable: true })
  assert.match(html, /fieldset disabled=""/)
  assert.doesNotMatch(html, /Continue with Google|Link Google/)
  for (const label of ['Username', 'Sign In', 'Forgot Password', 'First-Time Account Setup', 'secure booking verification']) assert.ok(html.includes(label))
})
test('configured credential form defaults to masked password and explicit unchecked persistence', () => {
  const html = render('PortalCredentialLogin', { capabilities: { accounts: { enabled: true }, google: { available: true } } })
  assert.doesNotMatch(html, /fieldset disabled=""/)
  assert.match(html, /type="password"/); assert.match(html, /autoComplete="current-password"/)
  assert.match(html, /aria-label="Show password"/); assert.doesNotMatch(html, /checked=""/)
  assert.doesNotMatch(html, /Continue with Google/)
})
test('new passwords use password-manager hints, bounded length and accessible toggle', () => {
  const html = render('PasswordField', { value: '', onChange() {}, autoComplete: 'new-password' })
  assert.doesNotMatch(html, /minLength=/); assert.match(html, /maxLength="128"/)
  assert.match(html, /autoComplete="new-password"/); assert.match(html, /aria-pressed="false"/)
})
test('account UI never persists credentials in browser storage or router state', () => {
  const source = fs.readFileSync(new URL('../components/dic/PortalAccountAccess.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /localStorage|sessionStorage|navigate\(/)
  assert.match(source, /setPassword\(''\)/)
  assert.match(source, /\/auth\/account\/link-booking\//)
  assert.match(source, /\/auth\/password\/reset\//)
})
test('account settings are absent until approved rollout is enabled', () => {
  assert.equal(render('PortalAccountSettings', {}), '')
})
test('username login and reviewed recovery never require email activation', () => {
  const html = render('PortalCredentialLogin', { capabilities: { accounts: { enabled: true } } })
  assert.match(html, /Username/)
  assert.match(html, /No email activation is required/)
  assert.match(html, /Recover username access without email/)
  assert.doesNotMatch(html, /Resend email verification|Confirm email ownership/)
  const recovery = render('PortalCredentialRecovery', { busy: false, onSubmit() {} })
  assert.match(recovery, /Administrator-issued recovery code/)
  assert.match(recovery, /15 minutes/)
  assert.match(recovery, /Confirm password/)
  assert.doesNotMatch(recovery, /type="email"|private-token/)
  const source = fs.readFileSync(new URL('../pages/ParticipantPortal.jsx', import.meta.url), 'utf8')
  assert.ok(source.includes('/auth/credentials/transition/'))
  for (const retired of ['/auth/email/verify/', '/auth/email/resend/', 'PortalEmailVerification']) assert.equal(source.includes(retired), false)
})


test('recovery issuance stays in the existing administrator operations workflow', async () => {
  const component = await server.ssrLoadModule('/src/components/operations/AccountRecovery.jsx')
  const html = renderToStaticMarkup(createElement(component.default, { orderReference: 'synthetic-reference' }))
  assert.match(html, /Your administrator password/)
  assert.match(html, /Ownership review reference/)
  assert.match(html, /System administrators only/)
  const source = fs.readFileSync(new URL('../components/operations/AccountRecovery.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /localStorage|sessionStorage|console[.]/)
  assert.ok(source.includes("postOperationsData('/account-recovery/'"))
  const operations = fs.readFileSync(new URL('../pages/Operations.jsx', import.meta.url), 'utf8')
  assert.ok(operations.includes("user?.role === 'System Administrator' && <AccountRecovery"))
})
