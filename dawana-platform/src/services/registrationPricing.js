// Draft estimates only. The backend remains authoritative for submitted orders.
export function categoryFee(category) {
  const raw = category?.current_fee_ngn
  if (raw === null || raw === undefined || String(raw).trim() === '') return null
  const fee = Number(raw)
  return Number.isFinite(fee) && fee > 0 ? fee : null
}

export function estimateRegistrationTotal(participants, categories) {
  if (!participants.length) return null
  let total = 0
  for (const participant of participants) {
    const fee = categoryFee(categories.find(item => String(item.id) === String(participant.categoryId)))
    if (fee === null) return null
    total += Math.round(fee * 100)
  }
  return total / 100
}
