(() => {
  'use strict'

  const eye = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" focusable="false"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>'
  const eyeOff = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" focusable="false"><path d="m3 3 18 18M10 5.2A12 12 0 0 1 12 5c6.5 0 10 7 10 7a19 19 0 0 1-3 3.8M6.3 6.3A21 21 0 0 0 2 12s3.5 7 10 7a12 12 0 0 0 5.7-1.4M10 10a3 3 0 0 0 4 4"/></svg>'
  const conceal = []

  function enhance() {
    document.querySelectorAll('input[type="password"]').forEach((input, index) => {
      if (input.closest('.dawana-password-field') || input.disabled || input.readOnly) return
      if (!input.id) input.id = `dawana-password-${index}`
      const label = input.labels?.[0]?.textContent.trim().replace(/[:*]\s*$/, '') || 'password'
      const wrapper = document.createElement('span')
      wrapper.className = 'dawana-password-field'
      input.before(wrapper)
      wrapper.append(input)
      const button = document.createElement('button')
      button.type = 'button'
      button.className = 'dawana-password-toggle'
      button.setAttribute('aria-controls', input.id)

      function setVisible(visible) {
        input.type = visible ? 'text' : 'password'
        const action = `${visible ? 'Hide' : 'Show'} password: ${label}`
        button.setAttribute('aria-label', action)
        button.setAttribute('title', action)
        button.setAttribute('aria-pressed', String(visible))
        button.innerHTML = visible ? eyeOff : eye
      }

      setVisible(false)
      button.addEventListener('click', () => setVisible(input.type === 'password'))
      wrapper.append(button)
      const hide = () => setVisible(false)
      conceal.push(hide)
      input.form?.addEventListener('submit', hide)
    })
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enhance)
  else enhance()
  window.addEventListener('pagehide', () => conceal.forEach(hide => hide()))
  window.addEventListener('pageshow', () => conceal.forEach(hide => hide()))
})()
