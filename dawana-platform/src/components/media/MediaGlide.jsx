import { useEffect, useRef, useState } from 'react'
import './MediaGlide.css'

export default function MediaGlide({children, count, label, className='', auto=true}) {
  const track=useRef(null)
  const region=useRef(null)
  const [paused,setPaused]=useState(false)
  const [hovered,setHovered]=useState(false)
  const [focused,setFocused]=useState(false)
  const [visible,setVisible]=useState(false)
  const [reduced,setReduced]=useState(false)
  const [overflow,setOverflow]=useState(false)
  useEffect(()=>{
    const query=window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync=()=>setReduced(query.matches)
    sync(); query.addEventListener('change',sync)
    return ()=>query.removeEventListener('change',sync)
  },[])
  useEffect(()=>{
    if (!region.current || !track.current) return
    const node=track.current
    const measure=()=>setOverflow(node.scrollWidth>node.clientWidth+2)
    measure()
    const resize=typeof ResizeObserver==='undefined'?null:new ResizeObserver(measure)
    resize?.observe(node)
    Array.from(node.children).forEach(child=>resize?.observe(child))
    const observer=typeof IntersectionObserver==='undefined'?null:new IntersectionObserver(entries=>setVisible(entries[0].isIntersecting),{threshold:.25})
    if(!observer)setVisible(true)
    observer?.observe(region.current)
    return ()=>{resize?.disconnect();observer?.disconnect()}
  },[count])
  function move(direction, automatic=false) {
    const node=track.current
    if(!node || node.children.length<2) return
    const first=node.children[0],second=node.children[1]
    const step=Math.abs(second.offsetLeft-first.offsetLeft)||first.getBoundingClientRect().width
    const end=node.scrollWidth-node.clientWidth
    const left=direction>0 && node.scrollLeft>=end-3 ? 0 : direction<0 && node.scrollLeft<=3 ? end : Math.max(0,Math.min(end,node.scrollLeft+direction*step))
    if(automatic && (document.hidden || Array.from(node.querySelectorAll('iframe,video,audio')).some(el=>el.tagName==='IFRAME'||!el.paused))) return
    node.scrollTo({left,behavior:reduced?'auto':'smooth'})
  }
  useEffect(()=>{
    if(!auto || !visible || !overflow || paused || hovered || focused || reduced) return
    const timer=window.setInterval(()=>move(1,true),5500)
    return ()=>window.clearInterval(timer)
  },[auto,visible,overflow,paused,hovered,focused,reduced,count])
  return <div ref={region} className="media-glide" role="region" aria-roledescription="carousel" aria-label={label}
    onPointerEnter={e=>{if(e.pointerType==='mouse')setHovered(true)}}
    onPointerLeave={e=>{if(e.pointerType==='mouse')setHovered(false)}}
    onPointerDown={e=>{if(track.current?.contains(e.target))setPaused(true)}} onFocusCapture={()=>setFocused(true)}
    onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget))setFocused(false)}}>
    {count>1 && overflow && <div className="media-glide-controls"><span>Swipe to explore</span><div>
      {auto && !reduced && <button className="media-glide-motion" type="button" onClick={()=>setPaused(v=>!v)} aria-label={paused?'Resume automatic movement':'Pause automatic movement'}>{paused?'Resume slides':'Pause slides'}</button>}
      <button type="button" onClick={()=>move(-1)} aria-label={'Previous '+label}>‹</button>
      <button type="button" onClick={()=>move(1)} aria-label={'Next '+label}>›</button>
    </div></div>}
    <div ref={track} className={'media-glide-track '+className} tabIndex={overflow?0:undefined} aria-label={label+' slides'} onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();move(e.key==='ArrowRight'?1:-1)}}}>{children}</div>
  </div>
}
