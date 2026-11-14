export function participantOrders(data) {
  if (!Array.isArray(data?.orders) || data.orders.some(order => !Array.isArray(order?.participants))) {
    throw new Error('Could not read your registrations. Please retry.')
  }
  return data.orders
}

export function participantExpiry(data) {
  const expires = Date.parse(data?.expires_at)
  if (data?.authenticated !== true || !Number.isFinite(expires) || expires <= Date.now()) {
    throw new Error('Could not confirm your participant session. Please sign in again.')
  }
  return expires
}

export function participantSessionAbsent(data, now = Date.now()) {
  const expiry = Date.parse(data?.expires_at)
  return data?.authenticated === false || (data?.authenticated === true && Number.isFinite(expiry) && expiry <= now)
}
