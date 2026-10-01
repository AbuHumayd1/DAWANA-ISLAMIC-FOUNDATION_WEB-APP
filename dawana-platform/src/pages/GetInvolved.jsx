import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'

const participationOptions = [
  { number: '01', title: 'Volunteer', copy: "Contribute your time, skills and experience to Dawana's educational, outreach and community initiatives.", action: 'Volunteer With Us', href: '#volunteer-section' },
  { number: '02', title: 'Partner With Us', copy: 'Collaborate with Dawana on meaningful initiatives, programmes and community development.', action: 'Explore Partnerships', href: '#partnership-section' },
  { number: '03', title: 'Support Dawana', copy: 'Support Islamic education, empowerment and community-service initiatives.', action: 'Support Dawana', href: '#support-dawana' },
  { number: '04', title: 'Join Our Community', copy: "Stay connected with Dawana's programmes, activities and educational content.", action: 'Stay Connected', href: '#community-section' },
]

const contributionAreas = [
  { symbol: 'T', title: 'Time', copy: 'Offer time in support of educational and community initiatives.' },
  { symbol: 'S', title: 'Skills', copy: 'Share practical skills that can support Dawana’s work.' },
  { symbol: 'E', title: 'Experience', copy: 'Contribute relevant experience to collaborative efforts.' },
  { symbol: 'C', title: 'Community', copy: 'Help strengthen connection and support across the community.' },
]

const supportAreas = [
  { title: 'Islamic Education', copy: 'Support educational activities and the sharing of beneficial knowledge.' },
  { title: 'Empowerment', copy: 'Contribute to initiatives that support learning and personal development.' },
  { title: 'Community Service', copy: 'Help sustain service and community-development initiatives.' },
]

function OptionCard({ option }) {
  return <article className="get-involved-option"><span className="get-involved-number">{option.number}</span><span className="get-involved-option-mark" aria-hidden="true">✦</span><h3>{option.title}</h3><p>{option.copy}</p><a href={option.href}>{option.action}<span aria-hidden="true">→</span></a></article>
}

function GetInvolvedHero() {
  return <section className="get-involved-hero"><div className="get-involved-hero-pattern" aria-hidden="true" /><Container><div className="get-involved-hero-content"><span className="get-involved-hero-label"><i /> Get Involved <i /></span><h1>Be Part of the Work</h1><p>There are many ways to contribute to Dawana's work. Share your time, skills, resources and support.</p><div className="get-involved-hero-actions"><a className="button button-gold" href="#volunteer-section">Volunteer With Us <span aria-hidden="true">→</span></a><a className="button get-involved-hero-secondary" href="#support-dawana">Support Dawana</a></div><div className="get-involved-hero-motto"><span /> Ridwanullahi Akbar <span /></div></div></Container></section>
}

function VolunteerSection() {
  return <section className="get-involved-volunteer" id="volunteer-section"><Container><div className="get-involved-volunteer-intro"><span className="eyebrow">Civic &amp; Scholarly Service</span><h2>Volunteer With Dawana</h2><p>Volunteering is an opportunity to contribute your time, skills and experience to beneficial work.</p><p>Contributions may support educational, outreach and community initiatives. Specific activities can be discussed when volunteer opportunities are announced.</p><button className="button" type="button" disabled>Volunteer applications to be announced</button></div><div className="get-involved-contributions">{contributionAreas.map((item) => <article key={item.title}><span aria-hidden="true">{item.symbol}</span><div><h3>{item.title}</h3><p>{item.copy}</p></div></article>)}</div></Container></section>
}

function PartnershipSection() {
  return <section className="get-involved-partnership-wrap" id="partnership-section"><Container><div className="get-involved-partnership"><div className="get-involved-partnership-mark" aria-hidden="true">✦</div><span className="eyebrow">Institutional Collaboration</span><h2>Partner With Dawana</h2><p>Dawana welcomes opportunities to collaborate with individuals and organisations whose work aligns with beneficial Islamic education, youth development and community wellbeing.</p><div className="get-involved-partnership-note"><strong>Shared purpose</strong><span>Collaboration details and enquiry arrangements will be shared when available.</span></div><a className="button" href="#community-section">Explore ways to connect <span aria-hidden="true">→</span></a></div></Container></section>
}

function SupportSection() {
  return <section className="get-involved-support" id="support-dawana"><Container><div className="get-involved-section-heading"><span className="eyebrow">Support &amp; contribution</span><h2>Support Dawana</h2><p>Your support can contribute to Dawana's educational, empowerment and community-service initiatives.</p></div><div className="get-involved-support-grid">{supportAreas.map((item, index) => <article key={item.title}><span className={`get-involved-support-symbol support-symbol-${index + 1}`} aria-hidden="true">{['01', '02', '03'][index]}</span><h3>{item.title}</h3><p>{item.copy}</p><span className="get-involved-support-status">Support details to be announced</span></article>)}</div><p className="get-involved-support-note">Donation arrangements and payment details will be provided when officially available.</p></Container></section>
}

function CommunitySection() {
  return <section className="get-involved-community" id="community-section"><Container><div><span className="eyebrow">Community &amp; Knowledge</span><h2>Stay Connected</h2><p>Stay connected with Dawana's programmes, activities and educational content.</p><div className="get-involved-community-actions"><Link className="button" to="/programs">Explore Programs <span aria-hidden="true">→</span></Link><Link className="button button-soft" to="/media">Explore Media <span aria-hidden="true">→</span></Link></div></div><aside className="get-involved-channel"><span className="get-involved-channel-icon" aria-hidden="true">▶</span><div><span className="eyebrow">Official channel</span><h3>Dawana on YouTube</h3><p>Visit the Foundation's official YouTube channel for educational content.</p><a href="https://www.youtube.com/@dawanaislamicfoundation" target="_blank" rel="noreferrer">Visit YouTube <span aria-hidden="true">↗</span></a></div></aside></Container></section>
}

export default function GetInvolved() {
  return <div className="public-page get-involved-page"><GetInvolvedHero /><section className="get-involved-framework"><Container><div className="get-involved-section-heading"><span className="eyebrow">Participation Framework</span><h2>How You Can Get Involved</h2><p>Dawana welcomes individuals and organisations who wish to contribute their time, skills, resources or support to beneficial initiatives.</p><span className="get-involved-heading-rule" /></div><div className="get-involved-options">{participationOptions.map((option) => <OptionCard key={option.number} option={option} />)}</div></Container></section><VolunteerSection /><PartnershipSection /><SupportSection /><CommunitySection /><section className="get-involved-closing"><Container><span className="get-involved-closing-icon" aria-hidden="true">✦</span><h2>Your Contribution Matters</h2><p>Through your time, skills, collaboration or support, you can contribute to Dawana's work.</p><div><a className="button button-gold" href="#volunteer-section">Volunteer With Dawana</a><a className="button get-involved-hero-secondary" href="#support-dawana">Support Dawana</a></div></Container></section></div>
}
