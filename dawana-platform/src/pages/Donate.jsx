import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero } from '../components/pages/PublicPage'

const supportAreas = [
  { number: '01', title: 'Islamic Education', copy: 'Support educational activities and opportunities for beneficial Islamic learning.' },
  { number: '02', title: 'Youth Development', copy: 'Help support programmes that engage and develop young people.' },
  { number: '03', title: 'Community Outreach', copy: "Contribute towards Dawana's wider outreach and community activities." },
]

function DonationIllustration() {
  return <div className="donate-page-art" role="img" aria-label="Decorative Dawana geometric motif"><div className="donate-page-arch"><span className="donate-page-star">✦</span><span className="donate-page-art-rule" /><span className="donate-page-art-caption">Dawah · Community · Service</span></div></div>
}

function DonationDetails() {
  return <aside className="donate-details-card" aria-label="Donation payment details"><span className="donate-details-icon" aria-hidden="true">✦</span><span className="eyebrow">Official payment information</span><h3>Official donation details coming soon.</h3><p>Verified donation instructions will be published here when provided by the Foundation.</p></aside>
}

function WhySupport() {
  return <section className="donate-why"><Container><div className="donate-section-heading"><span className="eyebrow">A shared contribution</span><h2>Why Your Support Matters</h2><p>Your contribution can help sustain Dawana’s work across these areas.</p></div><div className="donate-support-grid">{supportAreas.map((area) => <article key={area.number}><span>{area.number}</span><h3>{area.title}</h3><p>{area.copy}</p></article>)}</div></Container></section>
}

function MakeDonation() {
  return <section className="donate-main"><Container><div className="donate-main-copy"><span className="eyebrow">Contribute</span><h2>Make a Donation</h2><p>Your support helps Dawana continue its Dawah, youth, Tarbiyah and community activities.</p></div><DonationDetails /></Container></section>
}

export default function Donate() {
  return <div className="public-page donate-page"><PageHero eyebrow="Support Dawana" title="Support the Work of Dawana" description="Your support helps Dawana continue its Dawah, youth, Tarbiyah and community activities." aside={<DonationIllustration />} /><WhySupport /><MakeDonation /><section className="donate-contact-cta"><Container><div><span className="eyebrow gold-eyebrow">Questions about supporting Dawana?</span><h2>Get in Touch</h2><p>For enquiries about supporting the Foundation, please use the Contact page.</p></div><Link className="button button-gold" to="/contact">Contact Dawana <span aria-hidden="true">→</span></Link></Container></section></div>
}
