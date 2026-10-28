import { VerifiedContactInformation, FoundationContactForm } from '../components/foundation/FoundationExperience'
import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero } from '../components/pages/PublicPage'

const enquiryLinks = [
  { label: 'Programs', description: 'Learning and community initiatives', to: '/programs' },
  { label: 'Events', description: 'Foundation events and gatherings', to: '/events' },
  { label: 'Darul Islam Camp', description: 'Camp information and registration', to: '/dic' },
  { label: 'Partnerships', description: 'Explore collaboration opportunities', to: '/get-involved#partnership-section' },
  { label: 'Volunteering', description: 'Ways to contribute your skills', to: '/get-involved#volunteer-section' },
  { label: 'Media', description: 'Lectures and learning resources', to: '/media' },
]

function ContactInformation() { return <VerifiedContactInformation /> }

function ContactForm() { return <FoundationContactForm /> }

function ContactEnquiryLinks() {
  return <section className="contact-enquiry-section"><Container><div className="contact-section-heading"><span className="eyebrow">Choose a topic</span><h2>What would you like to ask about?</h2><p>Explore the relevant Foundation programme or contact our official channels above.</p></div><div className="contact-enquiry-grid">{enquiryLinks.map(item => <Link className="contact-enquiry-card" key={item.label} to={item.to}><span><strong>{item.label}</strong><small>{item.description}</small></span><span className="contact-enquiry-arrow" aria-hidden="true">→</span></Link>)}</div></Container></section>
}

export default function Contact() {
  return <div className="public-page contact-page"><PageHero eyebrow="Contact" title="Contact Us" description="For questions, programme enquiries, partnership matters and other requests, use the information and enquiry options below." /><section className="contact-main"><Container><ContactInformation /><ContactForm /></Container></section><ContactEnquiryLinks /></div>
}
