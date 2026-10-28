export function scanToken(value) {
  const text = String(value || '').trim()
  if (/^[A-Za-z0-9_-]{43}$/.test(text)) return text
  try {
    const url = new URL(text)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
        || url.pathname !== '/api/v1/dic/ids/verify/' || url.search) throw new Error()
    const token = url.hash.slice(1)
    if (/^[A-Za-z0-9_-]{43}$/.test(token)) return token
  } catch { /* Never echo the scanned value. */ }
  throw new Error('This is not a supported camper QR code. Try again or use manual lookup.')
}

export function movementPath(edition, participantId) {
  if (!/^[1-9]\d*$/.test(String(edition))) throw new Error('Choose a camp edition.')
  return `/movements/?${new URLSearchParams({ edition: String(edition), participant_id: participantId })}`
}

export function scanPath(edition) {
  if (!/^[1-9]\d*$/.test(String(edition))) throw new Error('Choose a camp edition.')
  return `/scan/?edition=${edition}`
}

export function stopCamera(stream) {
  stream?.getTracks().forEach(track => track.stop())
}
