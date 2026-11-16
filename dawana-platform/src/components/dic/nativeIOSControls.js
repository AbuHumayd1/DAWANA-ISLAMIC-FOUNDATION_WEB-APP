// Prefer built-in iPhone/iPad picker sheets and date wheels. Other devices
// retain the accessible custom calendar/combobox. No data or age-policy changes.
export function prefersNativeIOSControls(device = typeof navigator !== 'undefined' ? navigator : null) {
  if (!device) return false
  const agent = device.userAgent || ''
  return /iPhone|iPad|iPod/.test(agent)
    || (device.platform === 'MacIntel' && Number(device.maxTouchPoints) > 1)
}
