import { Component, createElement as h } from 'react'

export default class GlobalErrorBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() { return { failed: true } }

  render() {
    if (!this.state.failed) return this.props.children
    return h('main', { role: 'alert', className: 'container' },
      h('h1', null, 'This page could not be displayed'),
      h('p', null, 'Your payment status has not been changed. If checkout was interrupted, recover the existing registration before paying again.'),
      h('button', { type: 'button', onClick: () => window.location.reload() }, 'Reload this page'),
      h('p', null, h('a', { href: '/dic/register/recover' }, 'Recover an existing registration')))
  }
}
