import * as React from 'react'
import { boundDate, calendarKey, changeMonth, dateError, dateValue, parseDate } from './dateValue'
import './DateField.css'

const months = Array.from({ length: 12 }, (_, month) => new Intl.DateTimeFormat('en-GB', { month: 'long' }).format(new Date(2000, month, 1)))
const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const fullDate = (date) => new Intl.DateTimeFormat('en-GB', { dateStyle: 'full' }).format(date)

export default function DateField({ label, name, value, onChange, required = true, min, max }) {
  const lower = min || '0001-01-01'
  const upper = max || dateValue(new Date())
  const [open, setOpen] = React.useState(false)
  const [active, setActive] = React.useState(() => dateValue(boundDate(parseDate(value) || parseDate(upper), lower, upper)))
  const [error, setError] = React.useState('')
  const root = React.useRef(null)
  const input = React.useRef(null)
  const trigger = React.useRef(null)
  const focusDay = React.useRef(false)
  const selected = parseDate(value)
  const current = parseDate(active)
  const year = current.getFullYear()
  const month = current.getMonth()
  const first = parseDate(`${active.slice(0, 7)}-01`)
  const last = changeMonth(first, 1)
  last.setDate(0)
  const count = Math.ceil((first.getDay() + last.getDate()) / 7) * 7
  const heading = `${months[month]} ${year}`
  const previous = changeMonth(current, -1)
  const next = changeMonth(current, 1)
  const close = (restore = false) => { setOpen(false); if (restore) trigger.current?.focus({ preventScroll: true }) }
  const move = (date, focus = false) => { focusDay.current = focus; setActive(dateValue(boundDate(date, lower, upper))) }
  const show = () => { move(selected || parseDate(upper), true); setOpen(true) }

  React.useLayoutEffect(() => { input.current?.setCustomValidity(dateError(value, min, upper)) }, [value, min, upper])
  React.useLayoutEffect(() => {
    if (open && focusDay.current) {
      root.current?.querySelector(`[data-date="${active}"]`)?.focus({ preventScroll: true })
      focusDay.current = false
    }
  }, [open, active])
  React.useEffect(() => {
    if (!open) return undefined
    const outside = (event) => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('focusin', outside)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('focusin', outside) }
  }, [open])

  const choose = (iso) => {
    onChange({ target: { name, value: iso } })
    input.current?.setCustomValidity('')
    setError('')
    close(true)
  }

  return <div className="dic-field dic-date-field" ref={root} onKeyDown={(event) => {
    if (open && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true) }
  }}>
    <label htmlFor={name}>{label}{required && <b aria-hidden="true"> *</b>}</label>
    <div className="dic-date-input">
      <input ref={input} id={name} name={name} type="text" value={value} required={required} min={min} max={max}
        placeholder="YYYY-MM-DD" autoComplete="bday" inputMode="text" pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}"
        aria-invalid={Boolean(error) || undefined} aria-describedby={`${name}-hint${error ? ` ${name}-error` : ''}`}
        onChange={(event) => { const message = dateError(event.target.value, min, upper); event.target.setCustomValidity(message); if (error) setError(message); onChange(event) }}
        onFocus={() => setOpen(false)} onBlur={() => { if (input.current?.value) setError(input.current.validationMessage) }}
        onInvalid={(event) => setError(event.currentTarget.validationMessage)}
        onKeyDown={(event) => { if (event.key === 'ArrowDown' && event.altKey) { event.preventDefault(); show() } }} />
      <button ref={trigger} className="dic-date-trigger" type="button" aria-haspopup="dialog" aria-expanded={open} aria-controls={`${name}-calendar`}
        aria-label={selected ? `Change ${label.toLowerCase()}, ${fullDate(selected)}` : `Choose ${label.toLowerCase()}`}
        onClick={() => open ? close() : show()}>
        <svg width="21" height="21" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="3" fill="none" stroke="currentColor" strokeWidth="1.7" /><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
      </button>
    </div>
    <small id={`${name}-hint`} className="dic-date-hint">Year–month–day. Type a date or choose from the calendar.</small>
    {error && <small className="dic-field-error" id={`${name}-error`} role="alert">{error}</small>}
    {open && <div id={`${name}-calendar`} className="dic-calendar" role="dialog" aria-modal="false" aria-label={`Choose ${label.toLowerCase()}`}>
      <div className="dic-calendar-title"><span>{label}</span><button type="button" aria-label="Close calendar" onClick={() => close(true)}>×</button></div>
      <div className="dic-calendar-selects">
        <label>Month<select aria-label="Birth month" value={month} onChange={(event) => move(changeMonth(current, Number(event.target.value) - month))}>
          {months.map((title, index) => <option key={title} value={index} disabled={`${year.toString().padStart(4, '0')}-${String(index + 1).padStart(2, '0')}` < lower.slice(0, 7) || `${year.toString().padStart(4, '0')}-${String(index + 1).padStart(2, '0')}` > upper.slice(0, 7)}>{title}</option>)}
        </select></label>
        <label>Year<select aria-label="Birth year" value={year} onChange={(event) => move(changeMonth(current, (Number(event.target.value) - year) * 12))}>
          {Array.from({ length: Number(upper.slice(0, 4)) - Number(lower.slice(0, 4)) + 1 }, (_, index) => Number(upper.slice(0, 4)) - index).map((year) => <option key={year} value={year}>{year}</option>)}
        </select></label>
      </div>
      <div className="dic-calendar-navigation">
        <button type="button" aria-label="Previous month" disabled={dateValue(previous).slice(0, 7) < lower.slice(0, 7)} onClick={() => move(previous)}>‹</button>
        <strong id={`${name}-month`} aria-live="polite" aria-atomic="true">{heading}</strong>
        <button type="button" aria-label="Next month" disabled={dateValue(next).slice(0, 7) > upper.slice(0, 7)} onClick={() => move(next)}>›</button>
      </div>
      <table className="dic-calendar-grid" role="grid" aria-labelledby={`${name}-month`} aria-describedby={`${name}-keys`}>
        <thead><tr>{weekdays.map((day) => <th key={day} scope="col" abbr={day}>{day.slice(0, 2)}</th>)}</tr></thead>
        <tbody key={active.slice(0, 7)}>{Array.from({ length: count / 7 }, (_, week) => <tr key={week}>{Array.from({ length: 7 }, (_, weekday) => {
          const day = week * 7 + weekday - first.getDay() + 1
          if (day < 1 || day > last.getDate()) return <td key={weekday} />
          const iso = `${active.slice(0, 7)}-${String(day).padStart(2, '0')}`
          const disabled = iso < lower || iso > upper
          return <td key={weekday} aria-selected={value === iso} aria-disabled={disabled || undefined}>
            <button type="button" data-date={iso} tabIndex={active === iso ? 0 : -1} disabled={disabled} aria-label={fullDate(parseDate(iso))}
              aria-current={iso === dateValue(new Date()) ? 'date' : undefined}
              onFocus={() => { if (active !== iso) setActive(iso) }} onClick={() => choose(iso)}
              onKeyDown={(event) => { const target = calendarKey(parseDate(iso), event.key, event.shiftKey, lower, upper); if (target) { event.preventDefault(); move(target, true) } }}>{day}</button>
          </td>
        })}</tr>)}</tbody>
      </table>
      <p className="dic-calendar-help" id={`${name}-keys`}>Arrow keys move by day or week. Page Up/Down changes month; hold Shift to change year.</p>
      <button className="dic-calendar-done" type="button" onClick={() => close(true)}>Done</button>
    </div>}
  </div>
}
