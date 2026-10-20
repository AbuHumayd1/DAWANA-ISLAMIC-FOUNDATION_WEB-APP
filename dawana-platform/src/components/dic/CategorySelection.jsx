import * as React from 'react'
import './CategorySelection.css'

function ageLabel(minimum, maximum) {
  if (minimum == null && maximum == null) return 'No age restriction'
  if (minimum == null) return `Ages ${maximum} and under`
  if (maximum == null) return `Ages ${minimum} and over`
  if (minimum === maximum) return `Age ${minimum}`
  return `Ages ${minimum}–${maximum}`
}

function money(value) {
  return new Intl.NumberFormat('en-NG', {
    style: 'currency', currency: 'NGN', minimumFractionDigits: 2,
  }).format(Number(value))
}

function cutoffLabel(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'long', timeStyle: 'short', timeZone: 'Africa/Lagos',
  }).format(date)
}

export default function CategorySelection({ categories, value, onChange, earlyBirdCutoff }) {
  const groupId = React.useId()
  const hintId = `${groupId}-hint`

  return <fieldset className="dic-category-selection" aria-describedby={hintId}>
    <legend>Registration category <span aria-hidden="true">*</span><span className="dic-category-sr-only"> (required)</span></legend>
    <p id={hintId} className="dic-category-hint">Choose one category for this participant. The registration service confirms the final price at checkout.</p>
    <div className="dic-category-grid">
      {categories.map((category) => {
        const selected = String(value) === String(category.id)
        const early = category.current_price_type === 'early_bird'
        const available = category.current_fee_ngn != null
        const cutoff = early ? cutoffLabel(category.early_bird_cutoff_at || earlyBirdCutoff) : null
        const id = `${groupId}-${category.id}`
        return <label className={`dic-category-card${selected ? ' is-selected' : ''}${available ? '' : ' is-unavailable'}`} key={category.id} htmlFor={id}>
          <input id={id} type="radio" name="categoryId" value={String(category.id)} checked={selected} onChange={onChange} required disabled={!available} aria-labelledby={`${id}-name`} aria-describedby={`${id}-details`} />
          <span className="dic-category-copy">
            <span className="dic-category-heading">
              <span id={`${id}-name`} className="dic-category-name">{category.name}</span>
              {early && <span className="dic-category-badge">Early Bird</span>}
            </span>
            <span id={`${id}-details`} className="dic-category-details">
              <span className="dic-category-age">{ageLabel(category.minimum_age, category.maximum_age)}</span>
              <span className="dic-category-pricing">
                <span className="dic-category-fee">{available ? money(category.current_fee_ngn) : 'Fee unavailable'}</span>
                {early && category.regular_fee_ngn != null && <span className="dic-category-regular"><span className="dic-category-sr-only">Regular fee </span><s>{money(category.regular_fee_ngn)}</s></span>}
              </span>
              {available && <span className="dic-category-price-kind">{early ? 'Early-bird fee' : 'Regular fee'} · per participant</span>}
              {cutoff && <span className="dic-category-cutoff">Complete payment before {cutoff} (Africa/Lagos) for the early-bird fee.</span>}
            </span>
          </span>
        </label>
      })}
    </div>
    {categories.length === 0 && <p className="dic-category-hint" role="status">No registration categories are currently available.</p>}
  </fieldset>
}
