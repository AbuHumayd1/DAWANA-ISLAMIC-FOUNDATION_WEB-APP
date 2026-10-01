import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero } from '../components/pages/PublicPage'

const faqGroups = [
  {
    id: 'about-dawana',
    title: 'About Dawana',
    questions: [
      { id: 'who-is-dawana', question: 'Who is Dawana Islamic Foundation?', answer: <>Dawana Islamic Foundation is a Nigeria-based Islamic organization.</> },
      { id: 'what-does-dawana-do', question: 'What does Dawana do?', answer: <>Its work includes Islamic education, Da&apos;wah and outreach, spiritual development and Tarbiyah, community activities, youth development and empowerment, and a community ecosystem. Explore <Link to="/programs">Programs</Link> for listed activities.</> },
      { id: 'areas-of-work', question: 'What are Dawana’s main areas of work?', answer: <>The Foundation describes its areas as educational platforms; Da&apos;wah and Islamic outreach; spiritual development and Tarbiyah; members and community; youth development and empowerment; and businesses and the community ecosystem.</> },
    ],
  },
  {
    id: 'programs-activities',
    title: 'Programs & Activities',
    questions: [
      { id: 'physical-usrah', question: 'When and where does Physical Usrah take place?', answer: <>Physical Usrah takes place on Sundays in designated masjids. Specific local details can be confirmed through the <Link to="/programs">Programs page</Link>.</> },
      { id: 'tarbiyah', question: 'What are Tarbiyah sessions?', answer: <>Tarbiyah sessions are part of Dawana’s spiritual development activities. Current session details are listed on the <Link to="/programs">Programs page</Link> when available.</> },
      { id: 'tadhkirah', question: 'When and where is Tadhkirah?', answer: <>Tadhkirah is held on Fridays after Asr at Iponri Central Mosque, Iponri, Surulere, Lagos.</> },
      { id: 'online-learning', question: 'What online Islamic learning activities are available?', answer: <>The online explanation of Usūl ath-Thalāthah takes place on Fridays at 9 PM and alternates with Urjūzatul Mi&apos;iyyah. Check the <Link to="/programs">Programs page</Link> for current information.</> },
      { id: 'youth-outreach', question: 'What is Youth Outreach?', answer: <>Youth Outreach is a youth-focused outreach initiative. Registration is required and no payment is required. Further details, including announcements about Youth Outreach 2.0, will be shared when available.</> },
      { id: 'events', question: 'Where can I find information about events and seminars?', answer: <>Visit <Link to="/events">Events</Link> for event information. Dates and other details will be updated when confirmed.</> },
    ],
  },
  {
    id: 'darul-islam-camp',
    title: 'Darul Islam Camp',
    questions: [
      { id: 'what-is-dic', question: 'What is Darul Islam Camp (DIC)?', answer: <>DIC is a Foundation initiative that brings participants together for Islamic learning, spiritual development, youth engagement, reflection, and community interaction. Visit the <Link to="/dic">DIC page</Link> for camp information.</> },
      { id: 'register-dic', question: 'How can I register for DIC?', answer: <>Use the registration option on the <Link to="/dic">DIC page</Link>. The process includes participant details, a registration summary, checkout, payment, and confirmation. Camp dates, venue, and fee will be announced.</> },
      { id: 'multiple-dic', question: 'Can more than one participant be registered for DIC?', answer: <>Yes. Each participant has an individual registration, and multiple participant registrations can be grouped at checkout.</> },
      { id: 'dic-lectures', question: 'Where can I find DIC lectures?', answer: <>Visit the <Link to="/media?category=dic-lectures">DIC Lectures section in Media</Link>. Lecture content will be added when verified materials are available.</> },
    ],
  },
  {
    id: 'registration',
    title: 'Registration & Payment',
    questions: [
      { id: 'all-registration', question: 'Do all Dawana activities require registration?', answer: <>No. Physical Usrah, Tarbiyah sessions, Tadhkirah, and the online Usūl ath-Thalāthah and Urjūzatul Mi&apos;iyyah activities do not require registration. Youth Outreach and Symposiums require registration. DIC has its own registration process.</> },
      { id: 'activity-payment', question: 'Do Dawana activities require payment?', answer: <>Payment is not required for Physical Usrah, Tarbiyah sessions, Tadhkirah, the listed online learning activities, Youth Outreach, or Symposiums. DIC requires payment, but its fee has not yet been announced.</> },
      { id: 'dic-fee', question: 'How much does DIC registration cost?', answer: <>The DIC fee has not been announced. Check the <Link to="/dic">DIC page</Link> for updates; no fee is stated here until confirmed.</> },
    ],
  },
  {
    id: 'get-involved',
    title: 'Get Involved',
    questions: [
      { id: 'volunteer', question: 'How can I volunteer with Dawana?', answer: <>Visit <Link to="/get-involved#volunteer-section">Get Involved</Link> to learn about contributing your time, skills, and experience. Volunteer applications are not yet connected.</> },
      { id: 'partnership', question: 'How can I partner with Dawana?', answer: <>Read about collaboration on the <Link to="/get-involved#partnership-section">Partnership section</Link>. Contact arrangements will be shared when available.</> },
      { id: 'support', question: 'How can I support Dawana?', answer: <>Learn about ways to contribute on <Link to="/get-involved#support-dawana">Get Involved</Link>. Official donation arrangements and payment details have not yet been provided.</> },
    ],
  },
  {
    id: 'media',
    title: 'Media',
    questions: [
      { id: 'learning-content', question: 'Where can I find Dawana’s Islamic educational content?', answer: <>Visit the <Link to="/media">Media Center</Link> for educational content and learning resources. Materials will be listed as they become available.</> },
      { id: 'ramadan-tafseer', question: 'Where can I find Ramadan Tafseer materials?', answer: <>The <Link to="/media">Media Center</Link> includes a Ramadan Tafseer archive area. Recordings and notes will be added when verified materials are available.</> },
    ],
  },
  {
    id: 'general',
    title: 'General',
    questions: [
      { id: 'contact-dawana', question: 'How can I contact Dawana?', answer: <>Visit the <Link to="/contact">Contact page</Link> for enquiry options. Official email, telephone, address, and WhatsApp details will be provided when confirmed.</> },
    ],
  },
]

function FAQItem({ item, isOpen, onToggle }) {
  const triggerId = `faq-question-${item.id}`
  const answerId = `faq-answer-${item.id}`
  return <article className={`faq-item ${isOpen ? 'is-open' : ''}`}><h3><button className="faq-question" id={triggerId} type="button" aria-expanded={isOpen} aria-controls={answerId} onClick={onToggle}><span>{item.question}</span><span className="faq-toggle-icon" aria-hidden="true">{isOpen ? '−' : '+'}</span></button></h3><div className="faq-answer" id={answerId} role="region" aria-labelledby={triggerId} aria-hidden={!isOpen} inert={!isOpen}><div className="faq-answer-inner"><p>{item.answer}</p></div></div></article>
}

function FAQGroup({ group, openId, onToggle }) {
  return <section className="faq-group" id={`faq-${group.id}`} aria-labelledby={`faq-heading-${group.id}`}><div className="faq-group-heading"><span className="eyebrow">{group.title}</span><h2 id={`faq-heading-${group.id}`}>{group.title}</h2></div><div className="faq-list">{group.questions.map((item) => <FAQItem key={item.id} item={item} isOpen={openId === item.id} onToggle={() => onToggle(item.id)} />)}</div></section>
}

export default function FAQ() {
  const [openId, setOpenId] = useState(null)
  const toggleQuestion = (id) => setOpenId((currentId) => currentId === id ? null : id)

  return <div className="public-page faq-page"><PageHero eyebrow="Help & Information" title="Frequently Asked Questions" description="Find answers about Dawana’s activities, programmes, Darul Islam Camp, and ways to participate." /><section className="faq-content"><Container><nav className="faq-category-nav" aria-label="FAQ topics">{faqGroups.map((group) => <a key={group.id} href={`#faq-${group.id}`}>{group.title}</a>)}</nav><div className="faq-groups">{faqGroups.map((group) => <FAQGroup key={group.id} group={group} openId={openId} onToggle={toggleQuestion} />)}</div><aside className="faq-more-help"><div><span className="eyebrow">Still need help?</span><h2>Find the right place to start.</h2><p>Explore the relevant page for current programme, event, camp, and media information.</p></div><Link className="button button-small" to="/contact">Visit Contact <span aria-hidden="true">→</span></Link></aside></Container></section></div>
}
