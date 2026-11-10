import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import './CamperSelect.css'

// Controlled selection only: callers retain booking scope and invalidation rules.
export default function CamperSelect({ label, value, options, onChange, disabled = false, placeholder = 'Choose a camper' }) {
  const id = useId(), root = useRef(null), trigger = useRef(null), list = useRef(null)
  const [open, setOpen] = useState(false), [active, setActive] = useState(0)
  const [position, setPosition] = useState(null)
  const search = useRef({ text: '', at: 0 })
  const selected = options.findIndex(option => String(option.value) === String(value))
  const close = () => setOpen(false)
  const show = () => { setActive(Math.max(0, selected)); setOpen(true) }
  const choose = index => {
    const option = options[index]
    if (!option || disabled) return
    onChange(String(option.value)); close(); trigger.current?.focus()
  }
  useEffect(() => {
    if (!open) return
    list.current?.focus()
    const dismiss = event => { if (!root.current?.contains(event.target) && !list.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('pointerdown', dismiss)
    return () => document.removeEventListener('pointerdown', dismiss)
  }, [open])
  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const rect = trigger.current?.getBoundingClientRect()
      if (!rect) return
      const viewport = window.visualViewport
      const viewportTop = viewport?.offsetTop || 0, viewportLeft = viewport?.offsetLeft || 0
      const width = viewport?.width || window.innerWidth, height = viewport?.height || window.innerHeight
      const below = viewportTop + height - rect.bottom - 16, above = rect.top - viewportTop - 16
      const upwards = below < 180 && above > below
      const maxHeight = Math.max(44, Math.min(280, upwards ? above : below))
      const menuWidth = Math.max(0, Math.min(Math.max(rect.width, 220), width - 24))
      const desired = Math.min(options.length * 64 + 12, maxHeight)
      setPosition({ position:'fixed', margin:0, left:Math.max(viewportLeft + 12, Math.min(rect.left, viewportLeft + width - menuWidth - 12)),
        top:upwards ? Math.max(viewportTop + 12, rect.top - 8 - desired) : rect.bottom + 8,
        width:menuWidth, maxHeight:upwards ? desired : maxHeight, right:'auto', bottom:'auto' })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    window.visualViewport?.addEventListener('resize', place)
    return () => { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); window.visualViewport?.removeEventListener('resize', place) }
  }, [open, options.length])
  useEffect(() => {
    if (open) list.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [active, open])
  const expanded = open && !disabled && options.length > 0
  function keys(event) {
    if (event.key === 'Tab') { trigger.current?.focus(); close(); return }
    if (event.key === 'Escape') { event.preventDefault(); close(); trigger.current?.focus(); return }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault()
      setActive(index => event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1
        : (index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length)
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault(); choose(active)
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const now = event.timeStamp
      search.current = { text: (now - search.current.at < 700 ? search.current.text : '') + event.key.toLocaleLowerCase(), at: now }
      const index = options.findIndex(option => option.label.toLocaleLowerCase().startsWith(search.current.text))
      if (index >= 0) setActive(index)
    }
  }
  return <div className="camper-select" ref={root} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget) && !list.current?.contains(event.relatedTarget)) close() }}>
    <span id={`${id}-label`} className="camper-select-label">{label}</span>
    <button ref={trigger} type="button" className="camper-select-trigger" disabled={disabled || !options.length}
      aria-labelledby={`${id}-label ${id}-value`} aria-haspopup="listbox" aria-expanded={expanded}
      aria-controls={expanded ? `${id}-list` : undefined}
      onClick={() => expanded ? close() : show()}
      onKeyDown={event => { if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); show() } }}>
      <span id={`${id}-value`}>{selected >= 0 ? options[selected].label : placeholder}</span>
      <svg aria-hidden="true" viewBox="0 0 20 20"><path d="m5 8 5 5 5-5" /></svg>
    </button>
    {expanded && createPortal(<ul ref={list} id={`${id}-list`} className="camper-select-list" style={position || {visibility:'hidden'}} role="listbox" tabIndex={-1}
      aria-labelledby={`${id}-label`} aria-activedescendant={`${id}-option-${active}`} onKeyDown={keys}>
      {options.map((option, index) => <li id={`${id}-option-${index}`} key={String(option.value)} role="option"
        aria-selected={index === selected} data-active={index === active} onPointerMove={() => setActive(index)}
        onMouseDown={event => event.preventDefault()} onClick={() => choose(index)}>
        <span>{option.label}</span><span aria-hidden="true">{index === selected ? '✓' : ''}</span>
      </li>)}
    </ul>, document.body)}
  </div>
}
