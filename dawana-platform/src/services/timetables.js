export function timetablePath(item, type, day = '') {
  if (!/^[1-9]\d*$/.test(String(item)) || !['activities', 'food'].includes(type)) throw new Error('Choose a participant and timetable.')
  if (day && !/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error('Choose a camp date.')
  return '/timetables/?' + new URLSearchParams({ item_id: String(item), type, ...(day ? { date: day } : {}) })
}

export function adjacentDate(dates, day, step) {
  return dates[dates.findIndex(row => row.date === day) + step]?.date || ''
}
