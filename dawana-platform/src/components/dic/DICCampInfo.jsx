import { Link } from 'react-router-dom'
import { campDate } from '../../services/dicPresentation'
import './DICLandingRefinements.css'

function feeLabel(value) {
  if (value === null || value === undefined || String(value).trim() === '') return 'Awaiting confirmation'
  const fee = Number(value)
  return Number.isFinite(fee) && fee >= 0 ? new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(fee) : 'Awaiting confirmation'
}

export default function DICCampInfo({ options, optionsState, onRegister, onRetry }) {
  const canRegister = optionsState === 'ready' && options?.registration_is_open && !!options.categories?.length
  const status = optionsState === 'loading' ? 'Loading camp details…' : optionsState === 'error' ? 'Camp details are temporarily unavailable.' : canRegister ? 'Registration is open' : 'Registration is not currently open'
  const dates = options?.camp_start_date && options?.camp_end_date ? `${campDate(options.camp_start_date)} – ${campDate(options.camp_end_date)}` : 'To be announced'
  return <aside className="dic-camp-brief" aria-label="Camp and registration details">
    <div className="dic-brief-heading"><span className="eyebrow">CAMP DETAILS</span><span className={`dic-brief-status${canRegister ? ' is-open' : ''}`}>{canRegister ? 'Registration open' : 'Stay informed'}</span></div>
    <h2>{options?.name || 'Plan your DIC experience'}</h2>
    <dl className="dic-brief-facts">
      <div><dt>Camp dates</dt><dd>{dates}</dd></div>
      <div><dt>Venue</dt><dd>{options?.venue || 'To be announced'}</dd></div>
      <div><dt>Registration deadline</dt><dd>{campDate(options?.registration_close_date)}</dd></div>
      <div><dt>Registration fees</dt><dd>Based on participant category</dd></div>
    </dl>
    {optionsState === 'ready' && options?.categories?.length > 0 && <details className="dic-public-fees"><summary>View category fees</summary><div className="dic-fees-scroll"><table><caption>Configured fees — your final quote is confirmed by the server</caption><thead><tr><th scope="col">Category</th><th scope="col">Early Bird</th><th scope="col">Regular</th></tr></thead><tbody>{options.categories.map(category => <tr key={category.id}><th scope="row">{category.name}</th><td>{feeLabel(category.early_bird_fee_ngn)}</td><td>{feeLabel(category.regular_fee_ngn)}</td></tr>)}</tbody></table></div><p>Early Bird eligibility follows the approved deadline and server quote. Displaying fees does not open registration.</p></details>}
    <p className="dic-brief-note">View applicable fees and early-bird rates during registration.</p>
    <div className="dic-brief-actions">{optionsState === 'error' ? <button className="button" onClick={onRetry} type="button">Reload camp details</button> : <button className="button" onClick={onRegister} disabled={!canRegister} type="button">Register for DIC <span aria-hidden="true">↗</span></button>}
      {options?.venue_directions_url && <a href={options.venue_directions_url} target="_blank" rel="noopener noreferrer">Get directions ↗</a>}
    </div>
    <p className="dic-brief-note" role="status">{status}</p>
    <Link className="dic-recovery-link" to="/dic/register/payment-return">Already registered? Check your status</Link>
    <Link className="dic-recovery-link" to="/dic/participant">Participant / guardian sign in</Link>
  </aside>
}
