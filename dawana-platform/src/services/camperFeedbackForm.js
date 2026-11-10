// Presentation/payload validation only. The API remains authoritative.
export function validateExperience({ spec, ratings, choices, comments, recommend, channel }) {
  const errors = {}
  for (const key of Object.keys(spec.ratings)) {
    const value = choices[key]
    if ((!value || value === 'not_applicable') && spec.optional_ratings?.includes(key)) continue
    if (!ratings.some(([candidate]) => String(candidate) === value)) errors[key] = 'Choose a rating to continue.'
  }
  for (const key of Object.keys(spec.comments)) {
    if ((comments[key] || '').length > 1000) errors[`comment-${key}`] = 'Please use 1,000 characters or fewer.'
  }
  if (channel === 'final' && !['yes', 'no'].includes(recommend)) errors.recommend = 'Choose yes or no.'
  return errors
}

export function experiencePayload({ spec, ratings, choices, comments, recommend, channel, day }) {
  const errors = validateExperience({ spec, ratings, choices, comments, recommend, channel })
  if (Object.keys(errors).length) throw new Error('Complete the displayed questions before sending feedback.')
  const payload = { channel, day, ratings: {}, answers: {} }
  if (spec.version !== undefined) payload.questionnaire_version = spec.version
  for (const key of Object.keys(spec.ratings)) {
    if (choices[key] && choices[key] !== 'not_applicable') payload.ratings[key] = Number(choices[key])
  }
  for (const key of Object.keys(spec.comments)) payload.answers[key] = comments[key] || ''
  if (channel === 'final') payload.recommend = recommend === 'yes'
  return payload
}

export function confirmedFeedbackResult(result) {
  if (result?.accepted !== true) throw new Error('We could not confirm receipt. Please check before trying again.')
  return result.duplicate === true ? 'duplicate' : 'success'
}
