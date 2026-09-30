import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Container } from '../components/layout/SiteChrome'
import { PageHero } from '../components/pages/PublicPage'

const categories = [
  { label: 'Videos', glyph: '*', description: 'A home for recorded talks and educational sessions.' },
  { label: 'Audio', glyph: '*', description: 'Audio reminders, sermons, and study sessions.' },
  { label: 'Lectures', glyph: '*', description: 'A catalogue for lectures and scholarly addresses.' },
  { label: "Qur'an & Tafsir", glyph: '*', description: 'Quranic study and Tafsir resources.' },
  { label: 'Q&A', glyph: '?', description: 'Questions and answers for the learning archive.' },
  { label: 'Articles', glyph: '*', description: 'Written educational material and commentary.' },
  { label: 'PDFs & Resources', glyph: '*', description: 'Study notes, outlines, and downloadable PDFs.' },
]

// Placeholder records define the fields ready for verified media assets later.
const mediaItems = [
  { id: 'video-placeholder', category: 'Videos', type: 'VIDEO', glyph: '*', title: 'Video content to be added', description: 'Recorded talks and educational sessions will appear here when official content is available.', format: 'Video', speaker: 'To be announced', date: 'To be announced', duration: 'To be announced', thumbnail: '', externalUrl: '', embedUrl: '', downloadUrl: '' },
  { id: 'audio-placeholder', category: 'Audio', type: 'AUDIO', glyph: '*', title: 'Audio content to be added', description: 'Audio materials will be added to this archive when they are ready for publication.', format: 'Audio', speaker: 'To be announced', date: 'To be announced', duration: 'To be announced', thumbnail: '', externalUrl: '', embedUrl: '', downloadUrl: '' },
  { id: 'lecture-placeholder', category: 'Lectures', type: 'LECTURE', glyph: '*', title: 'Lecture content to be added', description: 'Lecture recordings and study materials will be listed here once officially published.', format: 'Video / Audio', speaker: 'To be announced', date: 'To be announced', duration: 'To be announced', thumbnail: '', externalUrl: '', embedUrl: '', downloadUrl: '' },
  { id: 'tafsir-placeholder', category: "Qur'an & Tafsir", type: 'QURAN & TAFSIR', glyph: '*', title: 'Quran and Tafsir content to be added', description: 'Quranic study and Tafsir materials will be available here when supplied.', format: 'Audio / Study notes', speaker: 'To be announced', date: 'To be announced', duration: 'To be announced', thumbnail: '', externalUrl: '', embedUrl: '', downloadUrl: '' },
  { id: 'qa-placeholder', category: 'Q&A', type: 'Q&A', glyph: '?', title: 'Q&A content to be added', description: 'A future archive for published questions and answers.', format: 'Audio / Clips', speaker: 'To be announced', date: 'To be announced', duration: 'To be announced', thumbnail: '', externalUrl: '', embedUrl: '', downloadUrl: '' },
  { id: 'article-placeholder', category: 'Articles', type: 'ARTICLE', glyph: '*', title: 'Article content to be added', description: 'Written educational materials will be added here when approved for publication.', format: 'Written document', speaker: 'To be announced', date: 'To be announced', duration: '', thumbnail: '', externalUrl: '', embedUrl: '', downloadUrl: '' },
  { id: 'resource-placeholder', category: 'PDFs & Resources', type: 'RESOURCE', glyph: '*', title: 'Resources to be added', description: 'Outlines, study notes, and downloadable PDFs will appear here when available.', format: 'PDF / Study notes', speaker: 'To be announced', date: 'To be announced', duration: '', thumbnail: '', externalUrl: '', embedUrl: '', downloadUrl: '' },
]

function MediaTypeBadge({ children }) {
  return <span className="media-type-badge">{children}</span>
}

function MediaAction({ item, featured = false }) {
  const label = item.externalUrl ? (item.type === 'VIDEO' || item.type === 'AUDIO' ? 'Play media' : 'View media') : 'Content to be added'
  if (item.externalUrl) return <a className={featured ? 'button' : 'media-card-action'} href={item.externalUrl} target="_blank" rel="noreferrer">{label} <span aria-hidden="true">&gt;</span></a>
  return <button className={featured ? 'button' : 'media-card-action'} type="button" disabled aria-label={`${label}: ${item.title}`}>{label}</button>
}

function FeaturedMedia() {
  const item = { type: 'FEATURED MEDIA', title: 'Featured media content to be added.', speaker: 'To be announced', date: 'To be announced', format: 'To be announced', externalUrl: '' }
  return <section className="media-featured-section"><Container><div className="media-section-heading"><div><span className="eyebrow">Featured media</span><h2>Selected from the archive</h2><p>Featured media content will be added when official materials are available.</p></div><span className="media-meta-caption">Details to be announced</span></div><article className="media-featured-card"><div className="media-featured-screen" aria-label="Featured media placeholder"><span className="media-placeholder-pattern" aria-hidden="true" /><button className="media-play-affordance" type="button" disabled aria-label="Featured media content is not yet available"><span aria-hidden="true">&gt;</span></button><span className="media-screen-caption">Featured media content to be added.</span></div><div className="media-featured-copy"><MediaTypeBadge>{item.type}</MediaTypeBadge><h3>{item.title}</h3><p>Recordings and educational materials will be added to this collection when approved for publication.</p><dl><div><dt>Media type</dt><dd>{item.format}</dd></div><div><dt>Speaker / author</dt><dd>{item.speaker}</dd></div><div><dt>Date</dt><dd>{item.date}</dd></div></dl><MediaAction item={item} featured /><small>Archive in preparation  Details to be announced</small></div></article></Container></section>
}

function ArchiveFeature({ title, eyebrow, copy, icon, action, to }) {
  return <article className="media-archive-feature"><span className="media-archive-icon" aria-hidden="true">{icon}</span><div className="media-archive-copy"><MediaTypeBadge>{eyebrow}</MediaTypeBadge><h3>{title}</h3><p>{copy}</p></div><div className="media-archive-status"><span>Archive in preparation</span><strong>Details to be announced</strong></div>{to ? <Link className="media-archive-action" to={to}>{action} <span aria-hidden="true">&gt;</span></Link> : <span className="media-archive-action" aria-label="Archive details to be announced">{action} <span aria-hidden="true">&gt;</span></span>}</article>
}

function ArchiveSections() {
  return <>
    <section className="media-archive-section"><Container><div className="media-section-heading"><div><span className="eyebrow">Programme archive</span><h2>Darul Islam Camp (DIC) Lectures</h2><p>Lectures and educational resources related to Darul Islam Camp.</p></div><Link className="button button-small" to="/dic">Explore DIC <span aria-hidden="true">&gt;</span></Link></div><ArchiveFeature eyebrow="Camp lecture archive" title="DIC lecture content to be added." copy="Lecture recordings, study notes, and related resources can be listed here when official materials are supplied." icon="" action="Explore DIC" to="/dic" /></Container></section>
    <section className="media-archive-section media-archive-alt"><Container><div className="media-section-heading"><div><span className="eyebrow">Annual archive</span><h2>Ramadan Tafseer</h2><p>Ramadan Tafseer materials from Dawana Islamic Foundation.</p></div><span className="media-meta-caption">Details to be announced</span></div><div className="media-ramadan-grid"><article><MediaTypeBadge>Past series archive</MediaTypeBadge><h3>Ramadan Tafseer archive</h3><p>Archive content to be added when verified recordings and notes are available.</p><div><span>Status</span><strong>To be announced</strong></div><div><span>Repository</span><strong>To be announced</strong></div></article><article><MediaTypeBadge>Programme information</MediaTypeBadge><h3>Ramadan Tafseer resources</h3><p>Information and materials will be added when officially supplied.</p><div><span>Status</span><strong>To be announced</strong></div><div><span>Repository</span><strong>To be announced</strong></div></article></div></Container></section>
  </>
}

function MediaCategoryFilter({ activeCategory, onChange }) {
  return <div className="media-category-grid" role="group" aria-label="Filter media by category">{categories.map(({ label, glyph, description }) => <button className={`media-category-tile ${activeCategory === label ? 'is-active' : ''}`} type="button" key={label} aria-pressed={activeCategory === label} onClick={() => onChange(label)}><span className="media-category-icon" aria-hidden="true">{glyph}</span><span className="media-category-copy"><strong>{label}</strong><small>{description}</small><em>Browse category <span aria-hidden="true">&gt;</span></em></span></button>)}</div>
}

function MediaCard({ item }) {
  return <article className="media-archive-card"><div className={`media-card-thumbnail media-thumb-${item.id.replace('-placeholder', '')}`}><span className="media-thumb-mark" aria-hidden="true">{item.glyph}</span><MediaTypeBadge>{item.type}</MediaTypeBadge><span className="media-thumb-status">Details to be announced</span></div><div className="media-card-content"><div className="media-card-overline"><span>{item.category}</span><span>{item.date}</span></div><h3>{item.title}</h3><p>{item.description}</p><div className="media-card-meta"><span>Format: {item.format}</span><span>Speaker / author: {item.speaker}</span></div><MediaAction item={item} /></div></article>
}

function MediaGrid({ activeCategory }) {
  const visibleItems = activeCategory === 'All' ? mediaItems : mediaItems.filter((item) => item.category === activeCategory)
  return <div className="media-grid-wrap" id="media-items"><div className="media-grid-heading"><h3>{activeCategory === 'All' ? 'Media archive' : activeCategory}</h3><span>{visibleItems.length} {visibleItems.length === 1 ? 'placeholder' : 'placeholders'}</span></div><div className="media-archive-grid" aria-live="polite">{visibleItems.map((item) => <MediaCard key={item.id} item={item} />)}</div></div>
}

function ResourceAndGallery() {
  return <section className="media-resource-section"><Container><div className="media-resource-grid"><article className="media-resource-panel"><div className="media-section-heading"><div><span className="eyebrow">Resources</span><h2>Learning materials</h2></div><MediaTypeBadge>PDF &amp; materials</MediaTypeBadge></div><p>Downloadable educational materials and study resources will be added when officially supplied.</p><div className="media-resource-row"><span aria-hidden="true">&gt;</span><div><strong>Resources to be added.</strong><small>Islamic educational documents  PDF</small></div><b>To be announced</b></div><div className="media-resource-row"><span aria-hidden="true">&gt;</span><div><strong>Resources to be added.</strong><small>Study notes and outlines  PDF</small></div><b>To be announced</b></div><small className="media-panel-footnote">Official materials will be verified before publication.</small></article><article className="media-resource-panel media-gallery-panel"><div className="media-section-heading"><div><span className="eyebrow">Gallery</span><h2>Visual archive</h2></div><MediaTypeBadge>Photographic archive</MediaTypeBadge></div><p>Verified Foundation photographs can be added to this section when available.</p><div className="media-gallery-placeholders" aria-label="Three gallery image placeholders">{[1, 2, 3].map((number) => <div key={number}><span aria-hidden="true">&gt;</span><small>To be added</small></div>)}</div><small className="media-panel-footnote">Gallery materials to be announced.</small></article></div></Container></section>
}

export default function Media() {
  const [activeCategory, setActiveCategory] = useState('All')
  return <div className="public-page media-page"><PageHero eyebrow="Media" title="Media" description="Explore Islamic lectures, reminders, educational sessions, and other media from Dawana Islamic Foundation." /><FeaturedMedia /><ArchiveSections /><section className="media-explore-section" id="media-collection"><Container><div className="media-section-heading"><div><span className="eyebrow">Explore media</span><h2>Browse the learning archive</h2><p>Choose a category to explore. Placeholder entries are clearly marked until official content is available.</p></div><button className="media-filter-reset" type="button" aria-pressed={activeCategory === 'All'} onClick={() => setActiveCategory('All')}>{activeCategory === 'All' ? 'All media selected' : 'View all media'}</button></div><MediaCategoryFilter activeCategory={activeCategory} onChange={setActiveCategory} /><MediaGrid activeCategory={activeCategory} /></Container></section><ResourceAndGallery /><section className="media-support"><Container><div><span className="eyebrow gold-eyebrow">Knowledge  Faith  Service</span><h2>Support the work of Dawana Islamic Foundation.</h2><p>Contribute to educational dissemination, knowledge preservation, and community programmes.</p></div><Link className="button button-gold" to="/programs">Explore programs <span aria-hidden="true">&gt;</span></Link></Container></section></div>
}
