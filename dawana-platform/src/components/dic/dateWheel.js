import { boundDate, dateValue, parseDate } from './dateValue.js'

// Work exclusively with local calendar dates. The registration and backend
// continue receiving the same YYYY-MM-DD value and unchanged age policies.
export const wheelISO = (year, month, day) => `${String(year).padStart(4,'0')}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`
export function daysInMonth(year, month) {
  const d = new Date(0)
  d.setFullYear(year, month, 0)
  return d.getDate()
}
export function wheelParts(iso) {
  const date = parseDate(iso)
  if (!date) return null
  return [date.getFullYear(), date.getMonth()+1, date.getDate()]
}
export function wheelClamp(parts, min, max) {
  const [year, month, day] = parts
  const iso = wheelISO(year, month, Math.min(day, daysInMonth(year, month)))
  return wheelParts(dateValue(boundDate(parseDate(iso), min, max)))
}
export function wheelChoices(parts, min, max) {
  const [year, month] = parts
  const [loYear, loMonth, loDay] = wheelParts(min)
  const [hiYear, hiMonth, hiDay] = wheelParts(max)
  const years = Array.from({length:hiYear-loYear+1},(_,i)=>loYear+i)
  const months = Array.from({length:12},(_,i)=>i+1).filter(m=>(year>loYear||m>=loMonth)&&(year<hiYear||m<=hiMonth))
  const days = Array.from({length:daysInMonth(year,month)},(_,i)=>i+1).filter(d=>(year>loYear||month>loMonth||d>=loDay)&&(year<hiYear||month<hiMonth||d<=hiDay))
  return { years, months, days }
}
