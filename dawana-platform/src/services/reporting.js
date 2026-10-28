export const reportDomains = ['overview','registration','finance','accommodation','attendance','academic','feedback','welfare']
export function reportingPath(values, format = '') {
  const source = values instanceof URLSearchParams ? values : new URLSearchParams(values)
  const domain = source.get('domain') || 'overview'
  if (!reportDomains.includes(domain)) throw new Error('Choose a supported report.')
  if (!/^[1-9]\d*$/.test(source.get('edition') || '')) throw new Error('Choose a camp edition.')
  if (format && !['csv','print'].includes(format)) throw new Error('Choose CSV or print.')
  const query = new URLSearchParams({edition: source.get('edition'), domain})
  for (const key of ['date_from','date_to','category','status','payment_status','q','channel','concern_category','urgency','sort','page']) {
    if (source.get(key)) query.set(key,source.get(key))
  }
  if (format) { query.delete('page'); query.set('export',format) }
  return '/reporting/?' + query.toString()
}
export function reportValue(value, unit = '') {
  if (value === null || value === undefined) return 'Unavailable'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (unit === 'NGN kobo') return new Intl.NumberFormat('en-NG',{style:'currency',currency:'NGN'}).format(Number(value)/100)
  if (unit === 'percent') return value + '%'
  return typeof value === 'number' ? new Intl.NumberFormat('en-NG').format(value) : String(value)
}
export const statusOptions = {
  overview:['submitted','confirmed','cancelled'],registration:['submitted','confirmed','cancelled'],
  finance:['initializing','pending','init_unknown','verify_pending','failed','amount_mismatch','superseded','reconcile','successful','duplicate_success'],accommodation:['active','reserve','inactive'],
  attendance:['arrival','departure','return'],welfare:['new','review','resolved','closed'],
}
