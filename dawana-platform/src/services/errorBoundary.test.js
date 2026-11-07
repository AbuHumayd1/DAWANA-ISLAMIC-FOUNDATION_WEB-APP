import test from 'node:test'
import assert from 'node:assert/strict'
import { renderToStaticMarkup } from 'react-dom/server'
import GlobalErrorBoundary from '../components/GlobalErrorBoundary.js'

test('boundary preserves normal children and provides accessible non-sensitive recovery', () => {
  const boundary = new GlobalErrorBoundary({ children: 'working page' })
  assert.equal(boundary.render(), 'working page')
  boundary.state = GlobalErrorBoundary.getDerivedStateFromError(new Error('sensitive exception'))
  const html = renderToStaticMarkup(boundary.render())
  assert.match(html, /role="alert"/)
  assert.match(html, /Recover an existing registration/)
  assert.doesNotMatch(html, /sensitive exception/)
  assert.equal(boundary.render().props.children[2].props.onClick instanceof Function, true)
})
