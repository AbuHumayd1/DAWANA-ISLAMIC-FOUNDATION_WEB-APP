import { useSyncExternalStore } from 'react'

export default function AppearanceControls() {
  const appearance = window.DawanaAppearance
  const state = useSyncExternalStore(appearance.subscribe, appearance.getSnapshot)
  return <div className="appearance-controls">
    <button className="theme-toggle" type="button" role="switch" aria-label="Dark mode" aria-checked={state.theme === 'dark'} onClick={appearance.toggle}>
      <span className="theme-toggle-track" aria-hidden="true"><span className="theme-toggle-thumb"><span className="theme-sun">&#9728;</span><span className="theme-moon">&#9790;</span></span></span>
    </button>
  </div>
}
