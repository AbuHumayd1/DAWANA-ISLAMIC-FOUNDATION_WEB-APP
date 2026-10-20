import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('../../../backend/dic/static/dic/password-toggle.js', import.meta.url), 'utf8')

function fixture() {
  function element() {
    return { attributes: {}, events: {}, children: [],
      setAttribute(name, value) { this.attributes[name] = value },
      addEventListener(name, action) { this.events[name] = action },
      append(child) { this.children.push(child); child.parent = this },
    }
  }
  const form = element()
  // Each field has its own submit listener, just as in a browser.
  form.addEventListener = (name, action) => { (form.events[name] ||= []).push(action) }
  const inputs = ['Password', 'Password confirmation'].map((label, index) => ({
    ...element(), id: `password${index + 1}`, type: 'password', form,
    labels: [{ textContent: `${label}:` }],
    closest() { return this.parent?.className === 'dawana-password-field' ? this.parent : null },
    before(wrapper) { this.wrapper = wrapper },
  }))
  for (const input of inputs) Object.defineProperty(input, 'value', {
    get() { throw new Error('Toggle must not read password values') },
    set() { throw new Error('Toggle must not write password values') },
  })
  const window = element()
  const document = {
    readyState: 'complete',
    querySelectorAll(selector) { assert.equal(selector, 'input[type="password"]'); return inputs },
    createElement: element,
  }
  vm.runInNewContext(source, { document, window })
  return { inputs, form, window }
}

test('password and confirmation toggle independently with accessible non-submit controls', () => {
  const { inputs } = fixture()
  const buttons = inputs.map(input => input.wrapper.children[1])
  for (let i = 0; i < inputs.length; i += 1) {
    assert.equal(buttons[i].type, 'button')
    assert.equal(buttons[i].attributes['aria-controls'], inputs[i].id)
    assert.equal(buttons[i].attributes['aria-pressed'], 'false')
    assert.match(buttons[i].attributes['aria-label'], /Show password/)
  }
  buttons[0].events.click()
  assert.equal(inputs[0].type, 'text')
  assert.equal(inputs[1].type, 'password')
  assert.equal(buttons[0].attributes['aria-pressed'], 'true')
  assert.match(buttons[0].attributes['aria-label'], /Hide password/)
  buttons[0].events.click()
  assert.equal(inputs[0].type, 'password')
})

test('submission and page lifecycle conceal passwords without reading or changing values', () => {
  const { inputs, form, window } = fixture()
  for (const event of ['submit', 'pagehide', 'pageshow']) {
    for (const input of inputs) input.wrapper.children[1].events.click()
    if (event === 'submit') form.events.submit.forEach(action => action())
    else window.events[event]()
    assert.ok(inputs.every(input => input.type === 'password'))
  }
})
