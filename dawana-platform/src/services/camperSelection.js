export function camperKey(order,participant) { return `${order.reference}:${participant.registration_item_id}` }
export function selectedCamper(orders,key) {
  const entries=orders.flatMap(order=>order.participants.map(participant=>({order,participant,key:camperKey(order,participant)})))
  return entries.find(entry=>entry.key===key)||entries[0]||null
}
