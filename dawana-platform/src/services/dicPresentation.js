import { categoryFee } from './registrationPricing.js'

export function campFeeRange(categories = []) {
  const fees = categories.map(categoryFee).filter(value => value !== null)
  return fees.length ? [Math.min(...fees), Math.max(...fees)] : null
}

export function campDate(value) {
  if (!value) return 'To be announced'
  const date = new Date(`${String(value).slice(0, 10)}T12:00:00Z`)
  return Number.isNaN(date.getTime()) ? 'To be announced' : new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Africa/Lagos' }).format(date)
}
