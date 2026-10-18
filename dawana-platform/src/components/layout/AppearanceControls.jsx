import { useSyncExternalStore } from 'react'

export default function AppearanceControls() {
  const appearance = window.DawanaAppearance
  const state = useSyncExternalStore(appearance.subscribe, appearance.getSnapshot)
  return <div className="appearance-controls" role="group" aria-label="Display preferences">
    <label>Theme<select value={state.theme} onChange={(event) => appearance.set({ theme: event.target.value })}>
      <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option>
    </select></label>
    <label>Reading size<select value={state.size} onChange={(event) => appearance.set({ size: event.target.value })}>
      <option value="standard">Standard</option><option value="comfortable">Comfortable (recommended)</option><option value="large">Large</option>
    </select></label>
  </div>
}
