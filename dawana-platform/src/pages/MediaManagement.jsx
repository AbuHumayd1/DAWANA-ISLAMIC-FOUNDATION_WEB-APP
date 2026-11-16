import './MediaManagement.css'

const libraries = [
  { model: 'campphotograph', title: 'Photos', symbol: '▧', subtitle: 'Camp photography', description: 'Review photographs and their publication details.' },
  { model: 'campvideo', title: 'Camp videos', symbol: '▷', subtitle: 'Video library', description: 'Manage video details and approved releases.' },
  { model: 'lecturerecording', title: 'Lecture recordings', symbol: '♫', subtitle: 'Learning archive', description: 'Organise lecture audio and recording information.' },
]

export default function MediaManagement() {
  const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/api\/v1\/?$/, '')
  return <main className="ops-media" aria-labelledby="ops-media-heading">
    <header className="ops-media-intro"><div><span className="ops-media-eyebrow">CAMP CONTENT · ADMINISTRATION</span><h1 id="ops-media-heading">Media management</h1><p>A single workspace for camp photos, videos and lecture recordings.</p></div><span className="ops-media-intro-icon" aria-hidden="true">▧</span></header>
    <div className="ops-media-section-title"><div><h2>Media libraries</h2><p>Choose a library to manage its records in the existing administration tools.</p></div><span className="ops-media-library-count">3 libraries</span></div>
    <div className="ops-media-grid">{libraries.map(({ model, title, symbol, subtitle, description }) => <article className="ops-media-card" key={model}><div className="ops-media-card-top"><span className="ops-media-symbol" aria-hidden="true">{symbol}</span><span className="ops-media-label">{subtitle}</span></div><h3>{title}</h3><p>{description}</p><a className="ops-media-link" href={`${base}/admin/dic/${model}/`}>Open {title.toLowerCase()}<span aria-hidden="true">↗</span></a></article>)}</div>
    <aside className="ops-media-guidance" aria-label="Publishing and storage information"><span className="ops-media-guidance-mark" aria-hidden="true">ⓘ</span><div><strong>Publishing &amp; storage</strong><p>Media publication requires separate publisher permission. Storage activation remains under owner control. Opening a library does not grant either permission.</p></div></aside>
  </main>
}
