import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero, ProjectCard } from '../components/pages/PublicPage'

export default function Projects() {
  return <div className="public-page projects-page"><PageHero eyebrow="Projects" title="Projects" description="Explore projects undertaken or supported by Da&apos;wãnã Islamic Foundation." /><section className="catalog-section projects-catalog"><Container><div className="section-lead"><h2>Our Projects</h2><p>Projects undertaken or supported by Da&apos;wãnã Islamic Foundation.</p></div><div className="projects-list"><ProjectCard title="Al-Qalam" /><ProjectCard title="Mosque Project" /></div></Container></section><section className="project-support"><Container><div><h2>Support the work of Da&apos;wãnã Islamic Foundation.</h2><p>Contribute to ongoing development and community projects.</p></div><Link className="button" to="/get-involved">Get Involved <span>↗</span></Link></Container></section><div className="watchword-strip"><Container><span><b>WATCHWORD:</b> &nbsp; رِضْوَانُ اللهِ أَكْبَرُ &nbsp; — &nbsp; <em>“Allah&apos;s Pleasure is the greatest”</em></span></Container></div></div>
}
