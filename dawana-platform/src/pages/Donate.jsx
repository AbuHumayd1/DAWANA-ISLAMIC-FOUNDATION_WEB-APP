import './Donate.css'
import { DonationExperience } from '../components/foundation/FoundationExperience'
import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero } from '../components/pages/PublicPage'

const supportAreas = [
  { number: '01', title: 'Islamic Education', copy: 'Support educational activities and opportunities for beneficial Islamic learning.' },
  { number: '02', title: 'Youth Development', copy: 'Help support programmes that engage and develop young people.' },
  { number: '03', title: 'Community Outreach', copy: "Contribute towards Dawana's wider outreach and community activities." },
]

function DonationDetails() { return <DonationExperience /> }

function WhySupport() {
  return <section className="donate-why"><Container><div className="donate-section-heading"><span className="eyebrow">A shared contribution</span><h2>Why Your Support Matters</h2><p>Your contribution can help sustain Dawana’s work across these areas.</p></div><div className="donate-support-grid">{supportAreas.map((area) => <article key={area.number}><span className="donate-support-number">{area.number}</span><div><h3>{area.title}</h3><p>{area.copy}</p></div><span className="donate-support-mark" aria-hidden="true">↗</span></article>)}</div></Container></section>
}

function MakeDonation() {
  return <section className="donate-main"><Container><div className="donate-main-copy"><span className="eyebrow">Contribute to the mission</span><h2>Make a Difference</h2><p>Every act of support can help sustain meaningful learning, youth development and community service.</p><p className="donate-main-hint">Donation collection will be available here when officially activated.</p></div><DonationDetails /></Container></section>
}

export default function Donate() {
  return <div className="public-page donate-page"><PageHero eyebrow="Support Dawana" title="Support the Work of Dawana" description="Your support helps Dawana continue its Dawah, youth, Tarbiyah and community activities." /><WhySupport /><MakeDonation /><section className="donate-contact-cta"><Container><div><span className="eyebrow gold-eyebrow">Let's make an impact together</span><h2>Have a Question?</h2><p>Interested in supporting our initiatives or exploring a partnership? We'd love to hear from you.</p></div><Link className="button button-gold" to="/contact">Contact Dawana <span aria-hidden="true">→</span></Link></Container></section></div>
}
