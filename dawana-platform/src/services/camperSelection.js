export function camperKey(order,participant) { return `${order.reference}:${participant.registration_item_id}` }
export function returnedCamperKey(orders, enrollmentId) {
  if (!enrollmentId) return null
  for (const order of orders) {
    const participant = order.participants.find(person => person.id === enrollmentId)
    if (participant) return camperKey(order, participant)
  }
  return null
}
export function selectedCamper(orders,key) {
  const entries=orders.flatMap(order=>order.participants.map(participant=>({order,participant,key:camperKey(order,participant)})))
  return entries.find(entry=>entry.key===key)||entries[0]||null
}
