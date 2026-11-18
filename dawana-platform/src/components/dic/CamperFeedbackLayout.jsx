import { Link } from 'react-router-dom'
import './CamperFeedbackWorld.css'

export function FeedbackWelcome({ channel = 'daily' }) {
  const copy = {
    daily: ['Daily feedback', 'Share your experience of today’s programme and meals.'],
    welfare: ['Submit a complaint', 'Report a welfare concern privately to the camp team.'],
    history: ['Complaint status', 'Review the progress of concerns you have submitted.'],
    final: ['Final camp evaluation', 'Reflect on the camp and help us improve future editions.'],
  }
  const [title,description] = copy[channel] || copy.daily
  return <header className="cf-welcome"><div><span className="cf-eyebrow">CAMPER WORLD · YOUR VOICE</span><h1>{title}</h1><p>{description}</p></div><span className="cf-welcome-art" aria-hidden="true">✧</span></header>
}

export function FeedbackChannelNav({ channel, onChange }) {
  return <nav className="cf-channel-nav" aria-label="Feedback and care">{[['daily','Daily feedback'],['welfare','Submit a complaint'],['history','Complaint status'],['final','Final camp evaluation']].map(([key,label])=>onChange ? <button key={key} type="button" aria-current={channel===key?'page':undefined} onClick={()=>onChange(key)}>{label}</button> : <Link key={key} aria-current={channel===key?'page':undefined} to={`/dic/feedback?channel=${key}`}>{label}</Link>)}</nav>
}
