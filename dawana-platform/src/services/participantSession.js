// Participant UI invalidation only. Never stores credentials or booking data.
export const participantSessionKey = 'dawana.participant.session-closed.v1'
const channelName = 'dawana-participant-session-v1'
const senders = new WeakMap()
function senderFor(browser) {
  if (!senders.has(browser)) senders.set(browser, `${Date.now()}:${Math.random()}`)
  return senders.get(browser)
}

export function participantSessionClosed(browser = window) {
  try { return browser.localStorage.getItem(participantSessionKey) !== null } catch { return false }
}
export function reopenParticipantSession(browser = window) {
  try { browser.localStorage.removeItem(participantSessionKey) } catch { /* server verification remains authoritative */ }
}
export function notifyParticipantSessionClosed(browser = window) {
  const marker = `${Date.now()}:${Math.random()}`
  try { browser.localStorage.setItem(participantSessionKey, marker) } catch { /* BroadcastChannel may still work */ }
  try { const channel = new browser.BroadcastChannel(channelName); channel.postMessage({ type: 'closed', sender: senderFor(browser) }); channel.close() } catch { /* storage fallback */ }
}
export function subscribeParticipantSessionClosed(clear, browser = window) {
  const storage = event => { if (event.key === participantSessionKey && event.newValue !== null) clear() }
  browser.addEventListener('storage', storage)
  let channel
  try { channel = new browser.BroadcastChannel(channelName); channel.onmessage = event => {
    if (event.data === 'closed' || (event.data?.type === 'closed' && event.data.sender !== senderFor(browser))) clear()
  } } catch { /* storage fallback */ }
  return () => { browser.removeEventListener('storage', storage); if (channel) { channel.onmessage = null; channel.close() } }
}

export async function revokeParticipantSession({ clear, revoke, success, failure }) {
  clear()
  try { await revoke(); success() } catch { failure() }
}
