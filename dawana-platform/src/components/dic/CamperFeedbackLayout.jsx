import { Link } from 'react-router-dom'
import './CamperFeedbackWorld.css'

export function FeedbackWelcome({ channel = 'daily' }) {
  const final = channel === 'final'
  return <header className="cf-welcome"><div><span className="cf-eyebrow">DIC CAMPER WORLD · YOUR VOICE MATTERS</span><h1>{final ? 'A camp to remember.' : 'A little reflection.\nA better camp, together.'}</h1><p>{final ? 'Look back on the moments that helped you grow.' : 'Tell us what made you smile, and what we can make better.'}</p></div><span className="cf-welcome-art" aria-hidden="true">✧</span></header>
}

export function FeedbackChannelNav({ channel, onChange }) {
  return <nav className="cf-channel-nav" aria-label="Feedback and care">{[['daily','Daily feedback'],['welfare','Submit a complaint'],['history','Complaint status'],['final','Final camp evaluation']].map(([key,label])=>onChange ? <button key={key} type="button" aria-current={channel===key?'page':undefined} onClick={()=>onChange(key)}>{label}</button> : <Link key={key} aria-current={channel===key?'page':undefined} to={`/dic/feedback?channel=${key}`}>{label}</Link>)}</nav>
}
