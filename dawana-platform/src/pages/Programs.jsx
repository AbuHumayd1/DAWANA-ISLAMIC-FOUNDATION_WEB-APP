import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero, ProgramCard } from '../components/pages/PublicPage'

const programs = [
  { title: 'Physical Usrah', category: 'Islamic Learning', schedule: 'Every Sunday', summary: 'Weekly & ongoing study circles', detail: 'Held physically in designated masjids.', registration: false, payment: false, cta: 'View Overview' },
  { title: 'Tarbiyah Sessions', category: 'Spiritual Development', schedule: 'Periodic Circles', summary: 'Weekly & ongoing study circles', detail: 'Spiritual nurture & character refinement', registration: false, payment: false, cta: 'View Overview' },
  { title: 'Tadhkirah', category: "Da'wah & Spiritual Development", schedule: 'Friday Evenings · After Asr', summary: 'Weekly & ongoing study circles', detail: 'Iponri Central Mosque, Iponri, Surulere, Lagos', registration: false, payment: false, cta: 'Venue & Assembly Details' },
  { title: 'Online Explanation of Usūl ath-Thalāthah', category: 'Islamic Learning', schedule: 'Fridays · 9:00 PM · Online', summary: 'Weekly & ongoing study circles', detail: "Virtual Broadcast via Da'wãnã Live Stream", note: 'Alternates weekly with the online explanation of Urjūzatul Mi’iyyah.', registration: false, payment: false, cta: 'Session Stream Info' },
  { title: 'Online Explanation of Urjūzatul Mi’iyyah', category: 'Islamic Learning', schedule: 'Fridays · 9:00 PM · Online', summary: 'Weekly & ongoing study circles', detail: 'Focus: Prophetic Biography (As-Seerah)', note: 'Alternates weekly with the online explanation of Usūl ath-Thalāthah.', registration: false, payment: false, cta: 'Session Stream Info' },
  { title: 'Youth Outreach', category: 'Youth Development & Empowerment', schedule: 'Registration Required', summary: 'Da’wah and youth-focused outreach initiative.', detail: 'Target: Adolescents, secondary & university youth', registration: true, payment: false, cta: 'Inquire / Waitlist' },
  { title: 'Symposiums', category: 'Youth & Major Initiatives', schedule: 'Registration Required', summary: "Academic and Islamic knowledge-focused symposiums organised by Da'wãnã Islamic Foundation.", detail: 'Thematic discourses & intellectual panels', registration: true, payment: false, cta: 'Announcement Notifications' },
  { title: 'Darul Islam Camp (DIC)', category: 'Major Initiative', schedule: 'Registration & Fee', summary: 'A major initiative bringing participants together for Islamic learning, spiritual development and community engagement.', detail: 'Comprehensive residential / intensive model', note: 'Process: Registration → Review → Payment → Confirmation', registration: true, payment: true, cta: 'Learn More / Register', featured: true },
]

const categories = [
  'All Programs',
  'Islamic Learning',
  'Spiritual Development & Tarbiyah',
  'Da’wah & Outreach',
  'Youth & Major Initiatives',
]

function matchesCategory(program, category) {
  if (category === 'All Programs') return true
  if (category === 'Islamic Learning') return program.category === category
  if (category === 'Spiritual Development & Tarbiyah') return program.category.includes('Spiritual Development')
  if (category === 'Da’wah & Outreach') return program.category.toLowerCase().includes('da') || program.title === 'Youth Outreach'
  return program.category.includes('Youth') || program.category === 'Major Initiative'
}

export default function Programs() {
  const [activeCategory, setActiveCategory] = useState('All Programs')
  const visiblePrograms = programs.filter((program) => matchesCategory(program, activeCategory))
  return <div className="public-page programs-page"><PageHero eyebrow="Programs & initiatives" title="Programs" description="Da&apos;wãnã Islamic Foundation&apos;s programs and initiatives for Islamic learning, spiritual development, Da’wah, youth engagement, and community development." aside={<><h2>Explore Da&apos;wãnã&apos;s Programs &amp; Initiatives</h2><p>Discover the educational, spiritual, Da’wah, youth and community initiatives of Da&apos;wãnã Islamic Foundation.</p><span className="aside-proof">✥ &nbsp; Authentic Foundation Initiatives</span></>} /><section className="filter-row"><Container><div className="filter-tabs">{categories.map((category) => <button key={category} type="button" className={activeCategory === category ? 'filter-active' : ''} aria-pressed={activeCategory === category} onClick={() => setActiveCategory(category)}>{category}</button>)}</div></Container></section><section className="catalog-section"><Container><div className="catalog-grid programs-grid">{visiblePrograms.map((program) => <ProgramCard key={program.title} program={program} />)}</div></Container></section><section className="participation-section"><Container><span className="eyebrow">Participation architecture</span><h2>How to Participate &amp; Engage</h2><p>Clear, straightforward access paths to all Da&apos;wãnã programs and learning assemblies.</p><div className="participation-grid"><article><b>1</b><h3>Open Weekly Halaqāt</h3><p>Physical Usrah, Friday Tadhkirah at Iponri Central Mosque, and alternating Friday night online treatises are open to the entire Muslim community.</p></article><article><b>2</b><h3>Cohort &amp; Specialty Programs</h3><p>Targeted initiatives like Youth Outreach and academic Symposiums require a brief delegate registration when enrollment windows open.</p></article><article><b>3</b><h3>Darul Islam Camp (DIC) Intake</h3><p>Registration for DIC follows an administrative workflow with confirmation details provided when available.</p></article></div></Container></section><section className="public-cta"><Container><span className="eyebrow">Administrative liaison desk</span><h2>Questions Regarding Study Circles or Cohort Registration?</h2><p>Details for the Secretariat Desk and program guide will be provided when officially available.</p><Link className="button button-gold" to="/contact">Contact Secretariat</Link></Container></section></div>
}
