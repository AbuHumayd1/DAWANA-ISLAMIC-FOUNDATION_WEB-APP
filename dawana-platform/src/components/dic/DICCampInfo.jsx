import { Link } from 'react-router-dom'
import { campDate, campFeeRange } from '../../services/dicPresentation'
import './DICLandingRefinements.css'

const money = value => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 2 }).format(value)

export default function DICCampInfo({ options, optionsState, onRegister, onRetry }) {
  const canRegister = optionsState === 'ready' && options?.registration_is_open && !!options.categories?.length
  const range = campFeeRange(options?.categories)
  const status = optionsState === 'loading' ? 'Loading camp details…' : optionsState === 'error' ? 'Camp details are temporarily unavailable.' : canRegister ? 'Registration is open' : 'Registration is not currently open'
  const dates = options?.camp_start_date && options?.camp_end_date ? `${campDate(options.camp_start_date)} – ${campDate(options.camp_end_date)}` : 'To be announced'
  return <aside className="dic-camp-brief" aria-label="Camp and registration details">
    <div className="dic-brief-heading"><span className="eyebrow">YOUR NEXT CAMP EXPERIENCE</span><span className={`dic-brief-status${canRegister ? ' is-open' : ''}`}>{canRegister ? 'Registration open' : 'Stay informed'}</span></div>
    <h2>{options?.name || 'Plan your DIC experience'}</h2>
    <dl className="dic-brief-facts">
      <div><dt>Camp dates</dt><dd>{dates}</dd></div>
      <div><dt>Venue</dt><dd>{options?.venue || 'To be announced'}</dd></div>
      <div><dt>Registration deadline</dt><dd>{campDate(options?.registration_close_date)}</dd></div>
      <div><dt>Fees per participant</dt><dd>{range ? range[0] === range[1] ? money(range[0]) : `${money(range[0])} – ${money(range[1])}` : 'Details coming soon'}</dd></div>
    </dl>
    <p className="dic-brief-note">Explore participant categories, prices and early-bird details when you register.</p>
    <div className="dic-brief-actions">{optionsState === 'error' ? <button className="button" onClick={onRetry} type="button">Reload camp details</button> : <button className="button" onClick={onRegister} disabled={!canRegister} type="button">Register for DIC <span aria-hidden="true">↗</span></button>}
      {options?.venue_directions_url && <a href={options.venue_directions_url} target="_blank" rel="noopener noreferrer">Get directions ↗</a>}
    </div>
    <p className="dic-brief-note" role="status">{status}</p>
    <Link className="dic-recovery-link" to="/dic/register/payment-return">Already registered? Check your status</Link>
  </aside>
}
