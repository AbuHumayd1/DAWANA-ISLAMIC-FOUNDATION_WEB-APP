(function (root) {
  'use strict'
  const key = 'dawana.appearance'
  const themes = ['system', 'light', 'dark']
  const sizes = ['standard', 'comfortable', 'large']
  const media = root.matchMedia('(prefers-color-scheme: dark)')
  const listeners = new Set()
  let state
  function read() {
    try { return JSON.parse(root.localStorage.getItem(key)) || {} } catch { return {} }
  }
  function normalize(value) {
    return { theme: themes.includes(value?.theme) ? value.theme : 'system', size: sizes.includes(value?.size) ? value.size : 'comfortable' }
  }
  function apply(value, persist) {
    state = normalize(value)
    const html = root.document.documentElement
    html.dataset.theme = state.theme === 'system' ? (media.matches ? 'dark' : 'light') : state.theme
    html.dataset.themePreference = state.theme
    html.dataset.readingSize = state.size
    html.style.colorScheme = html.dataset.theme
    if (persist) { try { root.localStorage.setItem(key, JSON.stringify(state)) } catch { /* Private browsing may disable storage. */ } }
    root.document.querySelectorAll('[data-appearance-theme]').forEach((control) => { control.value = state.theme })
    root.document.querySelectorAll('[data-appearance-size]').forEach((control) => { control.value = state.size })
    listeners.forEach((listener) => listener())
  }
  root.DawanaAppearance = {
    getSnapshot: () => state,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener) },
    set: (next) => apply({ ...state, ...next }, true),
  }
  apply(read(), false)
  media.addEventListener('change', () => { if (state.theme === 'system') apply(state, false) })
  root.addEventListener('storage', (event) => { if (event.key === key || event.key === null) apply(read(), false) })
  root.document.addEventListener('DOMContentLoaded', () => apply(state, false))
  root.document.addEventListener('change', (event) => {
    if (event.target.matches('[data-appearance-theme]')) root.DawanaAppearance.set({ theme: event.target.value })
    if (event.target.matches('[data-appearance-size]')) root.DawanaAppearance.set({ size: event.target.value })
  })
})(window)
