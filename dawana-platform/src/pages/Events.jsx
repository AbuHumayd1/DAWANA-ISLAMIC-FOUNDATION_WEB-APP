import { useEffect, useState } from 'react'
import { Container } from '../components/layout/SiteChrome'
import { EventCard, PageHero } from '../components/pages/PublicPage'

const events = [
  { title: 'Monthly Da’wah Seminar', label: 'Recurring Seminar', tone: 'green', symbol: '▣', summary: 'A recurring monthly Da’wah seminar.', details: [['Date', 'To be announced']], footer: 'Periodic Assembly' },
  { title: 'Quarterly Da’wah Seminar', label: 'Recurring Seminar', tone: 'green', symbol: '▦', summary: 'A recurring quarterly Da’wah seminar.', details: [['Date', 'To be announced']], footer: 'Quarterly Cadence' },
  { title: 'Ramadan Tafseer at Iponri', label: 'Ramadan Observance', tone: 'gold', symbol: '◫', summary: 'Ramadan Tafseer at Iponri.', details: [['Location', 'Iponri Central Mosque, Iponri, Surulere, Lagos'], ['Date', 'To be announced']], footer: 'Annual Seasonal Series' },
  { title: 'Other Scheduled Events', label: 'Upcoming Announcements', tone: 'green', symbol: '◷', summary: 'Other events will be announced as details become available.', details: [['Details', 'To be announced']], footer: 'Status: Pending Schedule', placeholder: true },
]

export default function Events() {
  const [year, setYear] = useState(new Intl.DateTimeFormat('en-NG',{timeZone:'Africa/Lagos',year:'numeric'}).format(new Date()))
  const [schedule, setSchedule] = useState({status:'loading',items:[],hasMore:false})
  useEffect(() => {
    const controller = new AbortController()
    setSchedule({status:'loading',items:[],hasMore:false})
    const api = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
    fetch(`${api}/dic/studio/public-itinerary/?year=${encodeURIComponent(year)}`, {
      credentials:'omit',cache:'no-store',signal:controller.signal,
    }).then(response => {if(!response.ok)throw new Error('Schedule unavailable');return response.json()})
      .then(data => {
        if(!Array.isArray(data.items))throw new Error('Invalid schedule')
        setSchedule({status:'ready',items:data.items,hasMore:!!data.has_more})
      }).catch(error => {if(error.name!=='AbortError')setSchedule({status:'error',items:[],hasMore:false})})
    return () => controller.abort()
  }, [year])
  const formatDate = (value, options) => new Intl.DateTimeFormat('en-NG',{timeZone:'Africa/Lagos',...options}).format(new Date(value))
  return <div className="public-page events-page"><PageHero eyebrow="Events" title="Events" description="Stay informed about Da'wãnã Islamic Foundation's scheduled events, seminars, Ramadan activities and annual itinerary." /><section className="catalog-section events-catalog"><Container><div className="section-lead"><h2>Scheduled &amp; Recurring Events</h2><p>Key seminars and periodic assemblies organized by Da&apos;wãnã Islamic Foundation.</p></div><div className="catalog-grid events-grid">{events.map((event) => <EventCard key={event.title} event={event} />)}</div></Container></section><section className="annual-section"><Container><span className="eyebrow">▣ &nbsp; Annual calendar</span><h2>Annual Itinerary</h2><p>Approved programme dates and venues are published here by the DAWANA media team.</p><div className="annual-itinerary-toolbar"><label htmlFor="itinerary-year">Programme year</label><select id="itinerary-year" value={year} onChange={e=>setYear(e.target.value)}>{Array.from({length:8},(_,i)=>String(new Date().getFullYear()-2+i)).map(y=><option key={y} value={y}>{y}</option>)}</select></div>
        {schedule.status==='loading' ? <p className="annual-card" role="status">Loading the approved itinerary…</p>
        : schedule.status==='error' ? <p className="annual-card" role="alert">The itinerary is temporarily unavailable. Please try again.</p>
        : schedule.items.length===0 ? <div className="annual-card"><span>▣</span><h3>No published schedule for {year} yet</h3><p>Confirmed programme dates will appear here once the Foundation publishes them.</p></div>
        : <div className="annual-itinerary-scroll"><table className="annual-itinerary-table"><thead><tr><th scope="col">Date &amp; time (WAT)</th><th scope="col">Programme</th><th scope="col">Venue</th><th scope="col">Status</th></tr></thead><tbody>{schedule.items.map(item=><tr key={item.id}><td><time dateTime={item.event_at}>{formatDate(item.event_at,{day:'numeric',month:'short',year:'numeric',hour:'numeric',minute:'2-digit'})}</time>{item.event_end_at && <div className="annual-itinerary-end">Until {formatDate(item.event_end_at,{day:'numeric',month:'short',hour:'numeric',minute:'2-digit'})}</div>}</td><td><strong>{item.title}</strong>{item.description && <p>{item.description}</p>}</td><td>{item.event_venue || 'To be announced'}</td><td><span className={'annual-itinerary-status annual-itinerary-status--'+item.event_status}>{item.event_status}</span></td></tr>)}</tbody></table>{schedule.hasMore && <p>More approved programmes may be available. Contact the Foundation for the complete itinerary.</p>}</div>}<div className="info-strip">ⓘ &nbsp; Event details will be announced when confirmed.</div></Container></section><div className="watchword-strip"><Container><strong>▱ &nbsp; Faith, Education &amp; Empowerment</strong><span><b>WATCHWORD:</b> &nbsp; رِضْوَانُ اللهِ أَكْبَرُ &nbsp; — &nbsp; <em>“Allah&apos;s Pleasure is the greatest”</em></span></Container></div></div>
}
