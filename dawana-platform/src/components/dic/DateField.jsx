import * as React from 'react'
import { createPortal } from 'react-dom'
import { dateError, dateValue, parseDate } from './dateValue'
import { wheelClamp, wheelChoices, wheelISO, wheelParts } from './dateWheel'
import './DateField.css'

const monthNames = Array.from({ length:12 }, (_,i) => new Intl.DateTimeFormat('en-GB',{month:'long'}).format(new Date(2000,i,1)))
const ROW_HEIGHT=36

function WheelColumn({ label, items, value, onChange, text }) {
  const ref = React.useRef(null)
  const timer = React.useRef(null)
  const drag = React.useRef(null)
  const selectedIndex = items.indexOf(value)
  // One centred item with an item above and below it. Keep DOM scroll and
  // React selection synchronized, without resetting an active finger drag.
  React.useLayoutEffect(() => {
    if (ref.current && selectedIndex >= 0 && !drag.current) {
      ref.current.scrollTop = selectedIndex * ROW_HEIGHT
    }
  }, [selectedIndex])
  React.useEffect(() => () => clearTimeout(timer.current), [])

  const settle = (element) => {
    clearTimeout(timer.current)
    const index = Math.max(0, Math.min(items.length - 1, Math.round(element.scrollTop / ROW_HEIGHT)))
    if (items[index] !== undefined) {
      element.scrollTop = index * ROW_HEIGHT
      if (items[index] !== value) onChange(items[index])
    }
  }
  const onScroll = event => {
    if (drag.current) return
    const element = event.currentTarget
    clearTimeout(timer.current)
    timer.current = setTimeout(() => settle(element), 120)
  }
  // iOS Safari sometimes gives the surrounding bottom sheet the gesture.
  // Drive the visible wheel directly under the finger as a fallback.
  const touchStart = event => {
    clearTimeout(timer.current)
    drag.current = { y: event.touches[0].clientY, top: ref.current.scrollTop }
    ref.current.classList.add('is-dragging')
  }
  const touchMove = event => {
    if (!drag.current) return
    const delta = event.touches[0].clientY - drag.current.y
    ref.current.scrollTop = drag.current.top - delta
    if (event.cancelable) event.preventDefault()
  }
  const touchEnd = () => {
    if (!drag.current) return
    drag.current = null
    ref.current.classList.remove('is-dragging')
    settle(ref.current)
  }
  return <div className="dic-wheel-column">
    <span className="dic-wheel-heading">{label}</span>
    <div className="dic-wheel-list" ref={ref} role="group" aria-label={`Scroll ${label.toLowerCase()}`}
      onScroll={onScroll} onTouchStart={touchStart} onTouchMove={touchMove} onTouchEnd={touchEnd} onTouchCancel={touchEnd}>
      {items.map(item => <button type="button" key={item} className={value === item ? 'is-selected' : ''}
        aria-pressed={value === item} onClick={() => onChange(item)}>{text(item)}</button>)}
    </div>
  </div>
}

export default function DateField({ label,name,value,onChange,required=true,min,max }) {
  const lower=min||'0001-01-01'
  const upper=max||dateValue(new Date())
  const [open,setOpen]=React.useState(false)
  const [error,setError]=React.useState('')
  const defaultDate=React.useCallback(() => {
    const upperParts=wheelParts(upper)
    const candidate=wheelISO(Math.max(1,upperParts[0]-18),upperParts[1],upperParts[2])
    return wheelClamp(wheelParts(value)||wheelParts(parseDate(candidate)?candidate:upper),lower,upper)
  },[value,lower,upper])
  const [draft,setDraft]=React.useState(defaultDate)
  const input=React.useRef(null)
  const opener=React.useRef(null)
  const dialog=React.useRef(null)
  const titleId=`${name}-wheel-title`
  React.useLayoutEffect(() => { input.current?.setCustomValidity(dateError(value,min,upper)) },[value,min,upper])
  React.useEffect(() => {
    if (!open) return undefined
    const escape=e=>{if(e.key==='Escape'){e.preventDefault();setOpen(false);opener.current?.focus({preventScroll:true})}}
    document.addEventListener('keydown',escape)
    const previous=document.activeElement
    dialog.current?.querySelector('.dic-wheel-done')?.focus({preventScroll:true})
    return ()=>{document.removeEventListener('keydown',escape);if(previous?.isConnected && document.activeElement===document.body) previous.focus({preventScroll:true})}
  },[open])
  const show=()=>{setDraft(defaultDate());setOpen(true)}
  const update=(index,item)=>setDraft(current=>wheelClamp(current.map((n,i)=>i===index?item:n),lower,upper))
  const choose=()=>{
    const iso=wheelISO(...draft)
    onChange({target:{name,value:iso}})
    input.current?.setCustomValidity('')
    setError('')
    setOpen(false)
    opener.current?.focus({preventScroll:true})
  }
  const {years,months,days}=wheelChoices(draft,lower,upper)
  return <div className="dic-field dic-date-field">
    <label htmlFor={name}>{label}{required && <b aria-hidden="true"> *</b>}</label>
    <div className="dic-date-input"><input ref={input} id={name} name={name} type="text" value={value||''} required={required} min={min} max={upper} placeholder="YYYY-MM-DD" autoComplete="bday" inputMode="numeric" pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}" aria-describedby={`${name}-hint${error?' '+name+'-error':''}`} aria-invalid={Boolean(error)||undefined}
      onPointerDown={e=>{if(e.pointerType==='touch'){e.preventDefault();show()}}} onChange={e=>{const message=dateError(e.target.value,min,upper);e.target.setCustomValidity(message);setError(message);onChange(e)}} onInvalid={e=>setError(e.currentTarget.validationMessage)} />
      <button type="button" ref={opener} className="dic-date-trigger" aria-haspopup="dialog" aria-expanded={open} aria-controls={`${name}-wheel`} aria-label={`Choose ${label.toLowerCase()}`} onClick={()=>open?setOpen(false):show()}><svg width="21" height="21" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="3" fill="none" stroke="currentColor" strokeWidth="1.7"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg></button>
    </div><small id={`${name}-hint`} className="dic-date-hint">Choose from the scrolling wheels or enter YYYY-MM-DD.</small>{error && <small className="dic-field-error" id={`${name}-error`} role="alert">{error}</small>}
    {open && typeof document !== 'undefined' && createPortal(<div className="dic-wheel-backdrop" onPointerDown={e=>{if(e.target===e.currentTarget) setOpen(false)}}><section ref={dialog} id={`${name}-wheel`} className="dic-wheel-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={e=>{if(e.key==='Tab'){const controls=[...e.currentTarget.querySelectorAll('button')];const first=controls[0],last=controls.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}}}>
      <div className="dic-wheel-title"><div><span className="dic-wheel-kicker">SELECT A DATE</span><h2 id={titleId}>{label}</h2></div><button type="button" className="dic-wheel-close" onClick={()=>{setOpen(false);opener.current?.focus({preventScroll:true})}} aria-label="Cancel date selection">×</button></div>
      <div className="dic-wheel-frame"><span className="dic-wheel-selection" aria-hidden="true"/><div className="dic-wheel-columns"><WheelColumn label="Day" items={days} value={draft[2]} onChange={n=>update(2,n)} text={n=>String(n).padStart(2,'0')}/><WheelColumn label="Month" items={months} value={draft[1]} onChange={n=>update(1,n)} text={n=>monthNames[n-1]}/><WheelColumn label="Year" items={years} value={draft[0]} onChange={n=>update(0,n)} text={n=>n}/></div></div>
      <p className="dic-wheel-preview" aria-live="polite">{new Intl.DateTimeFormat('en-GB',{dateStyle:'full'}).format(parseDate(wheelISO(...draft)))}</p>
      <div className="dic-wheel-actions"><button type="button" onClick={()=>{setOpen(false);opener.current?.focus({preventScroll:true})}}>Cancel</button><button type="button" className="dic-wheel-done" onClick={choose}>Use this date</button></div>
    </section></div>, document.body)}
  </div>
}
