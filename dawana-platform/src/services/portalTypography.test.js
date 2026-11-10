import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import postcss from 'postcss'
const read = relative => fs.readFileSync(new URL(relative, import.meta.url), 'utf8')

test('portal styles cannot apply a typography or layout rule outside the portal route', () => {
  for (const path of ['../components/dic/CamperExperience.css', '../components/dic/PremiumCamperPortal.css', '../components/dic/CamperWorld.css']) {
    const stylesheet = postcss.parse(read(path))
    stylesheet.walkRules(rule => {
      for (let parent = rule.parent; parent; parent = parent.parent) {
        if (parent.type === 'atrule' && /keyframes$/i.test(parent.name)) return
      }
      for (const selector of rule.selectors) assert.match(selector, /^\.cp-route(?:\s|$|:)/, `Leaking selector: ${selector}`)
    })
    assert.doesNotMatch(stylesheet.toString(), /@import|@font-face|font-family:\s*(?:Poppins|system-ui)/)
  }
})

test('portal uses shared font tokens with a restrained heading scale and consistent text roles', () => {
  const css = read('../components/dic/PremiumCamperPortal.css')
  assert.match(css, /font-family:var\(--font-body\)/)
  assert.match(css, /font:600 var\(--cp-heading-size\)\/1\.3 var\(--font-heading\)/)
  assert.match(css, /--cp-heading-size:1\.8rem/)
  assert.match(css, /--cp-heading-size:1\.65rem/)
  assert.match(css, /--cp-body-size:\.9375rem; --cp-small-size:\.875rem/)
  assert.doesNotMatch(css, /letter-spacing:\s*-[.\d]|font-size:\s*(?:2\.6|4\.2)rem/)
})

test('public chrome is excluded only for the participant route, not unrelated pages', () => {
  const source = read('../components/layout/SiteChrome.jsx')
  assert.ok(source.includes("if (/^\\/dic\\/participant(?:\\/|$)/.test(location.pathname)) return <main className=\"cp-route\">{children}</main>"))
  assert.match(source, /return <><Navbar \/><main>\{children\}<\/main><Footer \/><\/>/)
})
