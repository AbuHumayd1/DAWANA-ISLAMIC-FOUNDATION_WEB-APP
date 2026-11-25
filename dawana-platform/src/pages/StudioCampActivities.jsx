import { useState } from 'react'
import { studioUpload, studioPublish } from '../services/mediaStudioApi'

/** Maps directly to the existing approved camp-activity feed. */
export default function StudioCampActivities({ editions = [], onUpdated, canPublish = true }) {
  const [year, setYear] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [photo, setPhoto] = useState(null)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')
  async function publish(event) {
    event.preventDefault()
    if (!canPublish) return setFeedback('Your account needs permission to publish camp activities.')
    if (!year) return setFeedback('Choose the camp year first.')
    if (!title.trim()) return setFeedback('Enter the approved activity name.')
    if (!description.trim()) return setFeedback('Briefly describe the activity.')
    if (!photo) return setFeedback('Choose the activity flyer or photograph.')
    setBusy(true); setFeedback('')
    let uploaded = null
    try {
      uploaded = await studioUpload('activities', {
        edition: year, title: title.trim(), description: description.trim(),
        category: 'Camp activity', photograph: photo,
        alt_text: 'Activity flyer: ' + title.trim(),
      })
      await studioPublish('activities', uploaded.id, 'publish')
      setFeedback('Published to DIC → What to expect at camp.')
      setTitle(''); setDescription(''); setPhoto(null)
      if (event.currentTarget) event.currentTarget.reset()
      onUpdated?.()
    } catch (error) {
      setFeedback(uploaded
        ? 'The activity was saved but is not yet public. ' + (error.message || 'Check it before trying again.')
        : error.message || 'Unable to upload this activity. Please try again.')
    } finally { setBusy(false) }
  }
  return <section className="studio-direct-activity" aria-label="What to expect at camp">
    <div className="studio-direct-activity-heading"><h3>What to expect at camp</h3>
      <p>Add an approved camp activity here. It will appear directly in the “What to expect at camp” section of the DIC website.</p></div>
    {feedback && <p role="status" className="studio-appearance-message">{feedback}</p>}
    <form className="studio-appearance-form" onSubmit={publish}>
      <div className="studio-appearance-fields">
        <label>Camp year
          <select required disabled={busy} value={year} onChange={e=>setYear(e.target.value)}>
            <option value="">Choose camp year</option>
            {editions.map(item=><option key={item.id} value={item.id}>{item.name} ({item.year})</option>)}
          </select>
        </label>
        <label>Activity name
          <input required disabled={busy} maxLength={200} value={title}
            placeholder="e.g. Qur’an reflection circle" onChange={e=>setTitle(e.target.value)}/>
        </label>
        <label className="studio-appearance-wide">Activity flyer or photograph
          <input required disabled={busy} type="file" accept="image/jpeg,image/png,image/webp"
            onChange={e=>setPhoto(e.target.files?.[0]||null)}/>
        </label>
        <label className="studio-appearance-wide">Short description
          <textarea required disabled={busy} rows={3} maxLength={2000} value={description}
            placeholder="What can campers expect from this approved activity?"
            onChange={e=>setDescription(e.target.value)}/>
        </label>
      </div>
      <button type="submit" className="studio-appearance-primary" disabled={busy || !canPublish}>
        {busy ? 'Publishing…' : 'Publish to What to expect at camp'}
      </button>
    </form>
  </section>
}
