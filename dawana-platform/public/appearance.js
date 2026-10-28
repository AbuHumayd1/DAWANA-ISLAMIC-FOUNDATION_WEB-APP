(function (root) {
  'use strict'
  const key = 'dawana.appearance'
  const listeners = new Set()
  let state
  function read() {
    try {
      const saved = JSON.parse(root.localStorage.getItem(key))
      return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {}
    } catch { return {} }
  }
  function save(value) {
    try { root.localStorage.setItem(key, JSON.stringify(value)) } catch { /* Storage may be unavailable. */ }
  }
  function apply(value, persist) {
    state = { theme: value.theme === 'dark' ? 'dark' : 'light' }
    const html = root.document.documentElement
    html.dataset.theme = state.theme
    html.dataset.themePreference = state.theme
    delete html.dataset.readingSize
    html.style.colorScheme = state.theme
    // Retire only the obsolete size preference; retain any other saved fields.
    const cleaned = { ...value }
    delete cleaned.size
    if (persist || Object.hasOwn(value, 'size')) save(cleaned)
    root.document.querySelectorAll('[data-appearance-toggle]').forEach((control) => {
      control.setAttribute('aria-checked', String(state.theme === 'dark'))
    })
    listeners.forEach((listener) => listener())
  }
  root.DawanaAppearance = {
    getSnapshot: () => state,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener) },
    toggle: () => apply({ ...read(), theme: state.theme === 'dark' ? 'light' : 'dark' }, true),
  }
  apply(read(), false)
  root.addEventListener('storage', (event) => { if (event.key === key || event.key === null) apply(read(), false) })
  root.document.addEventListener('DOMContentLoaded', () => apply({ ...read(), theme: state.theme }, false))
  root.document.addEventListener('click', (event) => {
    if (event.target.closest?.('[data-appearance-toggle]')) root.DawanaAppearance.toggle()
  })
})(window)
