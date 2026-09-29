import { Link } from 'react-router-dom'
import { Container } from '../layout/SiteChrome'

export function PageHero({ eyebrow, title, description, aside }) {
  return <section className="public-hero"><Container><div className="public-hero-grid"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{aside && <div className="public-hero-aside">{aside}</div>}</div></Container></section>
}

export function StatusBadge({ children, tone = 'green' }) {
  return <span className={`status-badge status-${tone}`}>{children}</span>
}

export function ProgramCard({ program }) {
  return <article className={`catalog-card program-card ${program.featured ? 'program-featured' : ''}`}><div><div className="card-topline"><StatusBadge tone={program.registration ? 'gold' : 'green'}>{program.category}</StatusBadge><span className="card-schedule">{program.schedule}</span></div><h2>{program.title}</h2><p className="card-summary">{program.summary}</p>{program.note && <p className="card-note"><strong>Note:</strong> {program.note}</p>}<div className="card-details"><span>◉ &nbsp;{program.detail}</span><span>✓ &nbsp;Registration: {program.registration ? 'Required' : 'Not required'} · Payment: {program.payment ? 'Required' : 'Free'}</span></div></div><Link className={`card-cta ${program.featured ? 'card-cta-primary' : ''}`} to={program.featured ? '/dic' : '/programs'}>{program.cta}</Link></article>
}

export function EventCard({ event }) {
  return <article className={`catalog-card event-card ${event.placeholder ? 'event-placeholder' : ''}`}><div className="event-card-top"><StatusBadge tone={event.tone}>{event.label}</StatusBadge><span className="event-symbol">{event.symbol}</span></div><h2>{event.title}</h2><p className="card-summary">{event.summary}</p><div className="event-detail-box">{event.details.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><div className="event-footer">● &nbsp;{event.footer}</div></article>
}

export function ProjectCard({ title }) {
  return <article className="catalog-card project-page-card"><h2>{title}</h2><p className="card-summary">Project details to be announced.</p><div className="project-divider" /><Link className="card-cta card-cta-soft" to="/projects">View Project <span>↗</span></Link></article>
}
