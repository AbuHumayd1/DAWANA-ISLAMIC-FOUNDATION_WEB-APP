export const notApplicable = { value: 'None', label: 'None (Not applicable)' }
export const occupations = ['Civil Servant', 'Business', 'Trader', 'Entrepreneur', notApplicable]
export const maritalOptions = ['Single', 'Married', 'Divorcee', 'Widow / Widower', notApplicable]
export function participantChoiceLabel(value) {
  return value === notApplicable.value ? notApplicable.label : value
}
