import { ageOnDate } from '../../services/registrationPrivacy'

export default function GuardianFields({ participants = [], reference, contact, onChange, locked }) {
  const children = participants.filter(person => {
    const age = ageOnDate(person.dob, reference)
    return age !== null && age <= 5
  })
  if (!children.length) return null
  const guardians = participants.filter(person => {
    const age = ageOnDate(person.dob, reference)
    return person.sex?.toLowerCase() === 'female' && age !== null && age >= 18
  })
  const declarations = contact?.guardianRelationships || []
  const update = (childId, guardianId, confirmed) => onChange({ ...contact,
    guardianRelationships: [...declarations.filter(row => row.childId !== childId),
      ...(guardianId ? [{ childId, guardianId, confirmed }] : [])] })
  return <fieldset disabled={locked}><legend>Dependent children and guardians</legend>
    <p>Children aged 0–5 share an eligible female guardian’s house. Select the responsible adult in this booking. DIC staff review the accommodation relationship separately.</p>
    {children.map(child => {
      const row = declarations.find(item => item.childId === child.id)
      return <div key={child.id}>
        <label className="dic-field"><span>Guardian for {child.fullName}</span>
          <select value={row?.guardianId || ''} onChange={event => update(child.id, event.target.value, false)}>
            <option value="">Needs DIC assistance</option>
            {guardians.map(guardian => <option key={guardian.id} value={guardian.id}>{guardian.fullName}</option>)}
          </select>
        </label>
        {row?.guardianId && <label><input type="checkbox" checked={row.confirmed === true}
          onChange={event => update(child.id, row.guardianId, event.target.checked)} /> I am the selected guardian and confirm responsibility for this child.</label>}
      </div>
    })}
  </fieldset>
}
