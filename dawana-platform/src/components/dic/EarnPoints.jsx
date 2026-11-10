import './EarnPoints.css'

const frequencyLabels = { daily:'Daily', prayer:'Per prayer', rawatib:'Per Rawatib occurrence',
  target:'Per verified target', session:'Per session', once:'One-time milestone' }

export default function EarnPoints({ catalogue }) {
  if (!catalogue?.ready || !Array.isArray(catalogue.activities) || !catalogue.activities.length) return <section className="earn-points" aria-label="Earn Points"><h2>Earn Points</h2><p role="status">{catalogue?.message || 'Approved earning opportunities are not available yet.'}</p></section>
  const categories = [...new Set(catalogue.activities.map(row => row.category))]
  return <section className="earn-points" aria-labelledby="earn-points-title">
    <div className="cp-card-title"><div><span className="cp-kicker">MAKE YOUR CONTRIBUTION</span><h2 id="earn-points-title">Earn Points</h2></div></div>
    <p>Explore the approved DIC 2026 scoring activities. An authorized officer verifies completion and records points.</p>
    <p className="earn-points-guidance">Award eligibility requires verified registration, check-in and a valid house assignment. Activity-specific targets, thresholds and limits apply. Viewing an activity does not award points.</p>
    {categories.map(category => <details className="earn-points-category" key={category}>
      <summary>{category}</summary><ul>{catalogue.activities.filter(row => row.category === category).map(row => <li key={row.code}>
        <div><h3>{row.name}</h3><span>{row.kind === 'individual' ? 'Individual achievement · contributes to your house' : 'Collective house contribution'}</span>
          <small>{frequencyLabels[row.frequency] || 'Officer-verified occurrence'}{row.threshold ? ` · ${row.threshold}% participation threshold` : ''}</small>
        </div><strong>{row.points}<small>points</small></strong>
      </li>)}</ul>
    </details>)}
    <p className="earn-points-guidance">These are scoring rules, not scheduled tasks. Verified awards and any reversals appear in your contribution history.</p>
  </section>
}
