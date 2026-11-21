import PublishedCarousels from '../components/media/PublishedCarousels'
import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import PublishedStudioArchive from '../components/media/PublishedStudioArchive'
import './HomeHero.css'
import './HomeMobileCards.css'

const areas = [
  ['01', 'Our Educational Platforms', 'Building pathways to authentic Islamic knowledge for learners at every stage.'],
  ['02', "Da'wah & Islamic Outreach", 'Sharing beneficial reminders and creating spaces for meaningful engagement.'],
  ['03', 'Spiritual Development & Tarbiyah', 'Nurturing character, reflection and a living relationship with faith.'],
  ['04', 'Our Members / Community', 'Supporting connection, belonging and the shared work of community wellbeing.'],
  ['05', 'Youth Development & Empowerment', 'Encouraging young people to grow in confidence, purpose and service. The STEP Programme provided digital-skills training for Muslim youths in 2025.'],
  ['06', 'Our Businesses / Community Ecosystem', 'Developing practical initiatives that strengthen people and communities.'],
]

function SectionHeading({ eyebrow, title, children }) {
  return <div className="section-heading"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{children}</div>
}

function Arrow() { return <span aria-hidden="true" className="arrow">↗</span> }

function Home() {
  return <div className="home-page">
    <section className="hero"><div className="hero-pattern" /><Container className="hero-grid"><div className="hero-copy"><div className="identity-chip"><span />Da&apos;wãnã Islamic Foundation <b>•</b> <strong>EST. 1994</strong></div><h1>Knowledge.<br /><em>Faith.</em> Service.<br />Community.</h1><p>Dedicated to authentic Islamic knowledge, Da&apos;wah, spiritual development (Tarbiyah), youth development and community wellbeing.</p><div className="hero-actions"><Link className="button" to="/programs">Explore Our Programs <Arrow /></Link><Link className="button button-outline" to="/#who-we-are">Learn About Da&apos;wãnã <Arrow /></Link></div><div className="hero-meta"><div><span>Established</span><strong>1994 in Nigeria</strong></div><div><span>Origin</span><strong>The Islamic Front</strong></div><div><span>Core Mandate</span><strong>Knowledge &amp; Service</strong></div></div></div><div className="hero-art"><div className="watchword-panel"><div className="panel-pattern" /><div className="panel-top"><span>✦ Foundation watchword</span><b>EST. 1994</b></div><div className="watchword-core"><div className="arabic" lang="ar" dir="rtl">رِضْوَانُ اللهِ أَكْبَرُ</div><p>&quot;Allah&apos;s Pleasure is the greatest&quot;</p></div><div className="panel-bottom"><span>✧</span><div><small>Islamic foundation mandate</small><strong>Grounded in Qur&apos;an, Sunnah &amp; community upliftment</strong></div></div></div></div></Container></section>

    <section className="section who-section" id="who-we-are"><Container className="two-column"><div className="section-intro"><span className="eyebrow">Who we are</span><div className="former-line"><span>Formerly:</span><strong>The Islamic Front</strong></div></div><div className="who-copy"><h2>Building Knowledgeable, Spiritually Grounded and Empowered Communities</h2><p className="lead">Da&apos;wãnã Islamic Foundation is dedicated to the service of Allah and the spiritual, moral, and intellectual development of society. Rooted in authentic Islamic scholarship, we advance sound Islamic learning, structured tarbiyah (spiritual grooming), youth mentorship, and selfless community service.</p></div></Container></section>

    <section className="section areas-section" id="what-we-do"><Container><SectionHeading eyebrow="Six foundational areas of intervention" title="What We Do"><p>Our broad institutional mandates shaping long-term educational and societal development.</p></SectionHeading><div className="area-grid">{areas.map(([number, title, copy]) => <article className="area-card" key={title}><span className="card-number">{number}</span><h3>{title}</h3><p>{copy}</p></article>)}</div></Container></section>

    <section className="section programs-section" id="programs"><Container><SectionHeading eyebrow="Structured activities & initiatives" title="Ongoing Programs"><Link className="button button-small" to="/programs">Explore Programs <Arrow /></Link></SectionHeading><div className="program-feature"><div className="program-content"><div className="tag-row"><span>Islamic learning</span><span>Regular activity</span></div><h3>Physical Usrah</h3><p>A regular Islamic learning and spiritual development activity. Further program details will be announced as official information becomes available.</p><div className="meta-row"><span>Registration</span><strong>Not required</strong><span>Payment</span><strong>Free</strong></div></div></div></Container></section>

    <section className="projects-section" id="projects"><Container><SectionHeading eyebrow="Strategic initiatives" title="Institutional Projects"><Link className="button button-small" to="/projects">Explore Projects <Arrow /></Link></SectionHeading><div className="project-card"><div><div className="tag-row"><span className="tag-gold">Featured Project Spotlight</span><span>In Development</span></div><h3>Al-Qalam School</h3><p>Al-Qalam School is an educational initiative dedicated to providing quality primary and secondary education in an environment that promotes academic excellence, sound moral values, discipline, and character development.</p><div className="preview-meta"><span>☷ &nbsp; Primary &amp; Secondary Education</span><span>◷ &nbsp; Phased Implementation · Details Coming Soon</span></div></div></div></Container></section>

    <section className="dic-band" id="dic"><Container><div><span className="eyebrow gold-eyebrow">Flagship initiative</span><h2>Darul Islam Camp (DIC)</h2><p>An initiative of Da&apos;wãnã Islamic Foundation focused on Islamic learning, spiritual development and community building.</p></div><Link className="button button-gold" to="/dic">Explore DIC <Arrow /></Link></Container></section>

    <section className="section events-section" id="events"><Container><SectionHeading eyebrow="Time-specific gatherings" title="Events &amp; Gatherings"><Link className="button button-small" to="/events">View Events <Arrow /></Link></SectionHeading><div className="event-empty"><div><div className="tag-row"><span className="tag-gold">Recurring Da&apos;wah Activity</span></div><h3>Monthly Da&apos;wah Seminar</h3><p>A recurring Foundation activity. Confirmed dates and venues will be shared on the Events page when available.</p></div></div></Container></section>

    <section className="section media-section" id="media"><Container><SectionHeading eyebrow="Knowledge library" title="Learn. Listen. Watch."><Link className="button button-small" to="/media">Explore Media <Arrow /></Link></SectionHeading><p className="home-media-note">Watch approved video lectures and listen to published recordings in the Foundation Media Library.</p></Container></section>

    <PublishedCarousels destination="foundation_home" />
    <PublishedStudioArchive destination="foundation_home" />

    <section className="impact-band"><Container><span className="eyebrow gold-eyebrow">Impact / community</span><h2>Knowledge That Transforms.<br /><em>Service That Matters.</em></h2><p>When beneficial knowledge is shared and lived, it becomes a source of strength for individuals, families and communities.</p></Container></section>

    <section className="section involved-section" id="get-involved"><Container><SectionHeading eyebrow="Participate in the mission" title="Get Involved With Da&apos;wãnã"><Link className="button button-small" to="/get-involved">Get Involved <Arrow /></Link></SectionHeading><p className="section-copy">Every individual has talents, sincere effort, and resources to contribute toward elevating our communities. Join us across educational circles, scholarly partnerships, welfare operations, and community fellowship.</p></Container></section>

    <section className="donate-section home-donation-note" id="donate"><Container><span className="eyebrow">Supporting the mission</span><p>Official donation instructions are not yet available. Please refer to the Foundation's donation information page for verified updates.</p><Link to="/donate" className="text-link">Donation information <Arrow /></Link></Container></section>
    <section className="newsletter"><Container><div><span className="eyebrow">Stay connected</span><h2>Stay Connected With Da&apos;wãnã</h2><p>Receive updates about programs, events, Islamic educational content and Da&apos;wãnã initiatives.</p></div><form><label className="sr-only" htmlFor="email">Email address</label><input id="email" type="email" placeholder="Newsletter subscriptions coming soon" aria-label="Newsletter subscriptions are currently unavailable" disabled /><button className="button" type="button" disabled>Subscribe <Arrow /></button></form></Container></section>
  </div>
}

export default Home
