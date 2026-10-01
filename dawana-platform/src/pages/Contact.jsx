import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero } from '../components/pages/PublicPage'

const contactDetails = [
  { label: 'Official email', value: 'To be provided', note: 'An official email address will be published here.' },
  { label: 'Telephone', value: 'To be provided', note: 'An official telephone number will be published here.' },
  { label: 'Official address', value: 'To be provided', note: 'The Foundation location will be shared when confirmed.' },
  { label: 'WhatsApp', value: 'To be provided', note: 'An official WhatsApp contact will be added when available.' },
]

const enquiryOptions = [
  'General Enquiry',
  'Programme Enquiry',
  'DIC Enquiry',
  'Partnership Enquiry',
  'Volunteer Enquiry',
  'Other',
]

const enquiryLinks = [
  { label: 'Programs', description: 'Learning and community initiatives', to: '/programs' },
  { label: 'Events', description: 'Foundation events and gatherings', to: '/events' },
  { label: 'Darul Islam Camp', description: 'Camp information and registration', to: '/dic' },
  { label: 'Partnerships', description: 'Explore collaboration opportunities', to: '/get-involved#partnership-section' },
  { label: 'Volunteering', description: 'Ways to contribute your skills', to: '/get-involved#volunteer-section' },
  { label: 'Media', description: 'Lectures and learning resources', to: '/media' },
]

function ContactInformation() {
  return <section className="contact-information" aria-labelledby="contact-information-title"><div className="contact-section-heading"><span className="eyebrow">Contact information</span><h2 id="contact-information-title">How to reach us</h2><p>Official contact details will be added once provided by the Foundation.</p></div><div className="contact-details-grid">{contactDetails.map((item, index) => <article className="contact-detail-card" key={item.label}><span className="contact-detail-icon" aria-hidden="true">{['@', 'T', 'L', 'W'][index]}</span><div><h3>{item.label}</h3><strong>{item.value}</strong><p>{item.note}</p></div></article>)}</div><div className="contact-location-placeholder"><span className="contact-location-mark" aria-hidden="true">⌖</span><div><h3>Foundation location</h3><p>Official location to be provided.</p></div><span className="contact-location-status">Location details pending</span></div></section>
}

function ContactForm() {
  const [status, setStatus] = useState('')

  function handleSubmit(event) {
    event.preventDefault()
    setStatus('Your message has not been sent. The online contact form is not connected yet; please check back when official contact channels are available.')
  }

  return <section className="contact-form-panel" aria-labelledby="contact-form-title"><div className="contact-form-heading"><span className="eyebrow">Send an enquiry</span><h2 id="contact-form-title">How can we help?</h2><p>Complete the fields below to prepare your enquiry.</p></div><div className="contact-form-notice" role="note"><span aria-hidden="true">i</span><p>This form is not connected to a messaging service. Submitting it will not send or store your message.</p></div><form className="contact-form" onSubmit={handleSubmit} noValidate={false}><div className="contact-form-grid"><label>Full Name <span aria-hidden="true">*</span><input type="text" name="fullName" autoComplete="name" placeholder="Enter your full name" required /></label><label>Email Address <span aria-hidden="true">*</span><input type="email" name="email" autoComplete="email" placeholder="name@example.com" required /></label><label>Phone Number<input type="tel" name="phone" autoComplete="tel" placeholder="Optional" /></label><label>Subject <span aria-hidden="true">*</span><input type="text" name="subject" placeholder="What is your enquiry about?" required /></label><label className="contact-form-full">Enquiry Type <span aria-hidden="true">*</span><select name="enquiryType" defaultValue="" required><option value="" disabled>Select an enquiry type</option>{enquiryOptions.map((option) => <option key={option}>{option}</option>)}</select></label><label className="contact-form-full">Message <span aria-hidden="true">*</span><textarea name="message" rows="5" placeholder="Write your message" required /></label></div><button className="button contact-submit" type="submit">Send Message <span aria-hidden="true">→</span></button>{status && <p className="contact-form-status" role="status">{status}</p>}</form></section>
}

function ContactEnquiryLinks() {
  return <section className="contact-enquiry-section"><Container><div className="contact-section-heading"><span className="eyebrow">Choose a topic</span><h2>What would you like to ask about?</h2><p>Explore the relevant area while official enquiry channels are being prepared.</p></div><div className="contact-enquiry-grid">{enquiryLinks.map((item) => <Link className="contact-enquiry-card" key={item.label} to={item.to}><span><strong>{item.label}</strong><small>{item.description}</small></span><span className="contact-enquiry-arrow" aria-hidden="true">→</span></Link>)}</div></Container></section>
}

export default function Contact() {
  return <div className="public-page contact-page"><PageHero eyebrow="Contact" title="Contact Us" description="For questions, programme enquiries, partnership matters and other requests, use the information and enquiry options below." /><section className="contact-main"><Container><ContactInformation /><ContactForm /></Container></section><ContactEnquiryLinks /></div>
}
