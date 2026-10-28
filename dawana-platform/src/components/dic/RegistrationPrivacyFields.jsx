import Field from './RegistrationField'

export function AgeDisclosureFields({ participant, today, onChange, adultOnly = false }) {
  return <>
    <Field label="Age and date-of-birth disclosure" name="ageChoice" value={participant.ageChoice} onChange={onChange} options={[
      ...(!adultOnly ? [{ value: 'minor', label: 'Minor — under 18 (DOB required)' }] : []),
      { value: 'adult_dob', label: 'Adult — 18 or older, disclose DOB' },
      { value: 'adult_private', label: 'Adult — 18 or older, do not disclose exact DOB' },
    ]} />
    {participant.ageChoice === 'adult_private'
      ? <p className="dic-field-wide">By choosing this option, you confirm that this camper is aged 18 or older. Some age-restricted categories and housing or guardian decisions may require further review or an exact DOB.</p>
      : <Field label="Date of Birth" name="dob" value={participant.dob} onChange={onChange} type="date" max={today} />}
  </>
}

export function OptionalMeasurements({ participant, onChange }) {
  return <>
    <h3 className="dic-form-section-title">Measurements</h3>
    <p className="dic-field-wide">If you don't know your height or weight, you may leave these fields blank.</p>
    <Field label="Height (optional)" name="height" value={participant.height} onChange={onChange} required={false} type="number" min="0.01" step="0.01" placeholder="e.g. 175" unit="cm" />
    <Field label="Weight (optional)" name="weight" value={participant.weight} onChange={onChange} required={false} type="number" min="0.01" step="0.01" placeholder="e.g. 70" unit="kg" />
  </>
}
