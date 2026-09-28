import { Container } from '../components/layout/SiteChrome'
import { EventCard, PageHero } from '../components/pages/PublicPage'

const events = [
  { title: 'Monthly Da’wah Seminar', label: 'Recurring Seminar', tone: 'green', symbol: '▣', summary: 'A recurring monthly Da’wah seminar.', details: [['Date', 'To be announced']], footer: 'Periodic Assembly' },
  { title: 'Quarterly Da’wah Seminar', label: 'Recurring Seminar', tone: 'green', symbol: '▦', summary: 'A recurring quarterly Da’wah seminar.', details: [['Date', 'To be announced']], footer: 'Quarterly Cadence' },
  { title: 'Ramadan Tafseer at Iponri', label: 'Ramadan Observance', tone: 'gold', symbol: '◫', summary: 'Ramadan Tafseer at Iponri.', details: [['Location', 'Iponri Central Mosque, Iponri, Surulere, Lagos'], ['Date', 'To be announced']], footer: 'Annual Seasonal Series' },
  { title: 'Other Scheduled Events', label: 'Upcoming Announcements', tone: 'green', symbol: '◷', summary: 'Other events will be announced as details become available.', details: [['Details', 'To be announced']], footer: 'Status: Pending Schedule', placeholder: true },
]

export default function Events() {
  return <div className="public-page events-page"><PageHero eyebrow="Events" title="Events" description="Stay informed about Da'wãnã Islamic Foundation's scheduled events, seminars, Ramadan activities and annual itinerary." /><section className="catalog-section events-catalog"><Container><div className="section-lead"><h2>Scheduled &amp; Recurring Events</h2><p>Key seminars and periodic assemblies organized by Da&apos;wãnã Islamic Foundation.</p></div><div className="catalog-grid events-grid">{events.map((event) => <EventCard key={event.title} event={event} />)}</div></Container></section><section className="annual-section"><Container><span className="eyebrow">▣ &nbsp; Annual calendar</span><h2>Annual Itinerary</h2><p>Dates and details will be added as the yearly programme is confirmed.</p><div className="annual-card"><span>▣</span><h3>Yearly Programme in Preparation</h3><p>Dates and details will be added as the yearly programme is confirmed.</p></div><div className="info-strip">ⓘ &nbsp; Event details will be announced when confirmed.</div></Container></section><div className="watchword-strip"><Container><strong>▱ &nbsp; Faith, Education &amp; Empowerment</strong><span><b>WATCHWORD:</b> &nbsp; رِضْوَانُ اللهِ أَكْبَرُ &nbsp; — &nbsp; <em>“Allah&apos;s Pleasure is the greatest”</em></span></Container></div></div>
}
