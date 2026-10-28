export const feedbackChannels = { daily:'Daily Camper Feedback',final:'Final Camper Evaluation',staff:'Staff Feedback',lecturer:'Lecturer Feedback' }
export function feedbackPath(base, edition = '', filters = {}) {
  if (edition && !/^[1-9]\d*$/.test(String(edition))) throw new Error('Choose a valid camp edition.')
  const query = new URLSearchParams()
  if (edition) query.set('edition',edition)
  for (const [key,value] of Object.entries(filters)) if (value) query.set(key,value)
  return `${base}${query.size ? `?${query}` : ''}`
}
export function ratingLabel(value) { return value === null ? 'Below privacy threshold' : String(value) }
