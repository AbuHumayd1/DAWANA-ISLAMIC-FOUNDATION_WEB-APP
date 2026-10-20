// Calendar-only local dates: never round-trip birth dates through UTC.
export function parseDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null
  const [year, month, day] = value.split('-').map(Number)
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > 31) return null
  const date = new Date(0)
  date.setHours(12, 0, 0, 0)
  date.setFullYear(year, month - 1, day)
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null
}

export function dateValue(date) {
  return `${String(date.getFullYear()).padStart(4, '0')}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function dateError(value, min, max) {
  if (!value) return '' // The native required constraint handles empty fields.
  if (!parseDate(value)) return 'Enter a valid date in YYYY-MM-DD format.'
  if (min && value < min) return `Choose a date on or after ${min}.`
  if (max && value > max) return `Choose a date on or before ${max}.`
  return ''
}

export function boundDate(date, min, max) {
  const value = dateValue(date)
  return parseDate(value < min ? min : value > max ? max : value)
}

export function changeMonth(date, offset) {
  const result = new Date(date)
  const day = result.getDate()
  result.setDate(1)
  result.setMonth(result.getMonth() + offset)
  const last = new Date(result)
  last.setMonth(last.getMonth() + 1, 0)
  result.setDate(Math.min(day, last.getDate()))
  return result
}

export function calendarKey(date, key, shift, min, max) {
  let result = new Date(date)
  const days = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -date.getDay(), End: 6 - date.getDay() }
  if (key in days) result.setDate(result.getDate() + days[key])
  else if (key === 'PageUp' || key === 'PageDown') result = changeMonth(date, (key === 'PageUp' ? -1 : 1) * (shift ? 12 : 1))
  else return null
  return boundDate(result, min, max)
}
