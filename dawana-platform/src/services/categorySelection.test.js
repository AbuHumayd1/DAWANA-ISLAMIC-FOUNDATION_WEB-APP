import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

let server, CategorySelection
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
  CategorySelection = (await server.ssrLoadModule('/src/components/dic/CategorySelection.jsx')).default
})
after(async () => { await server?.close() })

const category = {
  id: 37, name: 'API category name', minimum_age: 8, maximum_age: 15,
  current_fee_ngn: '12000.00', regular_fee_ngn: '15000.00',
  early_bird_fee_ngn: '12000.00', current_price_type: 'early_bird',
  early_bird_cutoff_at: '2026-11-20T11:00:00Z',
}
const render = (data, props = {}) => renderToStaticMarkup(createElement(CategorySelection, {
  categories: [data], value: '', onChange() {}, ...props,
}))

test('early-bird card separates API name, ages, current price, regular price and Lagos cutoff', () => {
  const html = render(category)
  assert.match(html, /API category name/)
  assert.match(html, /Ages 8–15/)
  assert.match(html, /₦12,000\.00/)
  assert.match(html, /<s>₦15,000\.00<\/s>/)
  assert.match(html, /Early Bird/)
  assert.match(html, /20 November 2026 at 12:00/)
  assert.match(html, /Africa\/Lagos/)
})

test('unconfigured early bird renders only the API current regular fee', () => {
  const html = render({ ...category, current_price_type: 'regular', current_fee_ngn: '15000.00', early_bird_fee_ngn: null, early_bird_cutoff_at: null })
  assert.match(html, /₦15,000\.00/)
  assert.match(html, /Regular fee/)
  assert.doesNotMatch(html, /Early Bird|Not configured|dic-category-cutoff|<s>/)
})

test('expired early bird is governed by API price type rather than the client clock', () => {
  const html = render({ ...category, current_price_type: 'regular', current_fee_ngn: '15000.00' })
  assert.doesNotMatch(html, /Early Bird|₦12,000|<s>|dic-category-cutoff/)
})

test('preserves radio field name, category ID, selection and native required validation', () => {
  const html = render(category, { value: '37' })
  assert.match(html, /type="radio"/)
  assert.match(html, /name="categoryId"/)
  assert.match(html, /value="37"/)
  assert.match(html, /checked=""/)
  assert.match(html, /required=""/)
  assert.match(html, /<fieldset/)
  assert.match(html, /<legend>/)
  assert.match(html, /aria-labelledby=/)
  assert.match(html, /aria-describedby=/)
})

test('age bounds and missing pricing are explicit without invented prices', () => {
  for (const [minimum_age, maximum_age, text] of [[null, null, 'No age restriction'], [18, null, 'Ages 18 and over'], [null, 12, 'Ages 12 and under'], [10, 10, 'Age 10']]) {
    assert.ok(render({ ...category, minimum_age, maximum_age }).includes(text))
  }
  const html = render({ ...category, current_fee_ngn: null })
  assert.match(html, /Fee unavailable/)
  assert.match(html, /disabled=""/)
  assert.doesNotMatch(html, /₦0\.00/)
})

test('cutoff uses edition fallback and omits invalid or absent dates', () => {
  const html = render({ ...category, early_bird_cutoff_at: null }, { earlyBirdCutoff: category.early_bird_cutoff_at })
  assert.match(html, /20 November 2026/)
  assert.doesNotMatch(render({ ...category, early_bird_cutoff_at: 'invalid' }), /dic-category-cutoff/)
})
