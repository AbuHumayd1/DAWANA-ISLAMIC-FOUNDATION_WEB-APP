import * as React from 'react'
import './RegistrationControls.css'
import DateField from './DateField'

// A select-only combobox with a native backing control for form validity/values.
export function RegistrationSelect({ id, name = id, label, value, onChange, options, required = false }) {
  const items = options.map((option) => typeof option === 'string' ? { value: option, label: option } : option)
  const [open, setOpen] = React.useState(false)
  const [active, setActive] = React.useState(-1)
  const [invalid, setInvalid] = React.useState(false)
  const root = React.useRef(null)
  const trigger = React.useRef(null)
  const search = React.useRef({ text: '', time: 0 })
  const selected = items.findIndex((item) => String(item.value) === String(value))
  const enabled = items.map((item, index) => !item.disabled ? index : -1).filter((index) => index >= 0)
  const listId = `${id}-options`

  React.useEffect(() => {
    if (!open) return undefined
    const outside = (event) => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('focusin', outside)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('focusin', outside)
    }
  }, [open])

  const show = () => { setActive(selected >= 0 && !items[selected].disabled ? selected : enabled[0] ?? -1); setOpen(true) }
  const choose = (index) => {
    if (!items[index] || items[index].disabled) return
    onChange({ target: { name, value: String(items[index].value) } })
    setInvalid(false)
    setOpen(false)
    trigger.current?.focus({ preventScroll: true })
  }
  const keyDown = (event) => {
    if (event.key === 'Tab') { setOpen(false); return }
    if (event.key === 'Escape') { event.preventDefault(); setOpen(false); return }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault()
      if (!open) {
        show()
        if (event.key === 'Home') setActive(enabled[0] ?? -1)
        if (event.key === 'End') setActive(enabled.at(-1) ?? -1)
        return
      }
      const position = enabled.indexOf(active)
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? enabled.length - 1
        : (position + (event.key === 'ArrowDown' ? 1 : -1) + enabled.length) % enabled.length
      setActive(enabled[next] ?? -1)
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      if (open) choose(active)
      else show()
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault()
      const now = event.timeStamp
      const text = now - search.current.time < 700 ? search.current.text + event.key : event.key
      search.current = { text, time: now }
      const index = enabled.find((index) => items[index].label.toLowerCase().startsWith(text.toLowerCase()))
      setOpen(true)
      if (index !== undefined) setActive(index)
    }
  }

  return <div className="dic-field dic-select-field" ref={root}>
    <label id={`${id}-label`} htmlFor={id}>{label}{required && <b aria-hidden="true"> *</b>}</label>
    <select className="dic-select-native" name={name} value={value} required={required} tabIndex={-1} aria-hidden="true"
      onChange={onChange} onInvalid={(event) => { event.preventDefault(); setInvalid(true); trigger.current?.focus(); }}>
      <option value="">Select {label.toLowerCase()}</option>
      {items.map((item) => <option key={item.value} value={item.value} disabled={item.disabled}>{item.label}</option>)}
    </select>
    <button ref={trigger} id={id} type="button" className="dic-select-trigger" role="combobox"
      aria-labelledby={`${id}-label ${id}-value`} aria-expanded={open} aria-controls={listId}
      aria-haspopup="listbox" aria-required={required} aria-invalid={invalid || undefined}
      aria-describedby={invalid ? `${id}-error` : undefined}
      aria-activedescendant={open && active >= 0 ? `${id}-option-${active}` : undefined}
      onClick={() => open ? setOpen(false) : show()} onKeyDown={keyDown}>
      <span id={`${id}-value`} className={selected < 0 ? 'is-placeholder' : ''}>{items[selected]?.label || `Select ${label.toLowerCase()}`}</span>
      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
    <ul id={listId} role="listbox" aria-labelledby={`${id}-label`} className={`dic-select-options ${open ? 'is-open' : ''}`} inert={!open}>
      {items.map((item, index) => <li id={`${id}-option-${index}`} key={item.value} role="option"
        aria-selected={selected === index} aria-disabled={item.disabled || undefined}
        className={active === index ? 'is-active' : ''}
        onPointerDown={(event) => event.preventDefault()} onPointerMove={() => { if (!item.disabled) setActive(index) }} onClick={() => choose(index)}>
        <span>{item.label}</span><span aria-hidden="true">{selected === index ? '✓' : ''}</span>
      </li>)}
    </ul>
    {invalid && <small className="dic-field-error" id={`${id}-error`} role="alert">Please select {label.toLowerCase()}.</small>}
  </div>
}

export default function RegistrationField({ label, name, value, onChange, type = 'text', required = true, wide = false, options, placeholder, unit, min, max, step }) {
  const [error, setError] = React.useState('')
  if (type === 'date') return <DateField label={label} name={name} value={value} onChange={onChange} required={required} min={min} max={max} />
  if (options) return <RegistrationSelect id={name} name={name} label={label} value={value} onChange={onChange} options={options} required={required} />
  return <div className={`dic-field ${wide ? 'dic-field-wide' : ''}`}>
    <label htmlFor={name}>{label}{required && <b aria-hidden="true"> *</b>}</label>
    <span className="dic-input-wrap"><input id={name} name={name} value={value} onChange={(event) => { setError(''); onChange(event) }}
      type={type} required={required} min={min} max={max} step={step} placeholder={placeholder}
      aria-invalid={Boolean(error) || undefined} aria-describedby={error ? `${name}-error` : undefined}
      onInvalid={(event) => setError(event.currentTarget.validationMessage)} />{unit && <small>{unit}</small>}</span>
    {error && <small className="dic-field-error" id={`${name}-error`} role="alert">{error}</small>}
  </div>
}
