import { useState } from 'react'
import { participantCardPath, staffCardPath } from '../../services/participantIdentity'
import './DigitalIDPresentation.css'

const formats = [['pvc','PVC card'],['a6','A6 badge'],['portrait','PDF badge']]

export default function DigitalIDPresentation({ card, onClose, staff = false }) {
  const [format, setFormat] = useState('pvc')
  const cardPath = staff ? staffCardPath : participantCardPath
  const chosen = formats.find(([key]) => key === format)?.[1] || 'PVC card'
  return <section className="participant-id-view id-presentation id-presentation-compact" aria-label="My Digital ID">
    <header className="id-presentation-heading"><div><span className="id-eyebrow">ISSUED CAMP IDENTIFICATION</span><h1>{staff ? 'Participant Digital ID' : 'My Digital ID'}</h1><p>{card.name}</p><span className="participant-id-number">{card.participant_number}</span></div><button type="button" className="id-back" onClick={onClose}>← Back</button></header>
    <section className="id-card-workspace" aria-label="Card formats and downloads"><h2>Choose your card format</h2><p>Select a format, then open it to print or save a copy.</p>
      <div className="id-format-tabs" role="group" aria-label="Card format">{formats.map(([key,label]) => <button type="button" key={key} aria-pressed={format === key} onClick={() => setFormat(key)}>{label}</button>)}</div>
      <div className="id-card-active"><div><strong>{chosen}</strong><small>Issued for {card.name}</small></div><div className="id-card-actions"><a className="id-primary-action" href={cardPath(card.id,format)} referrerPolicy="no-referrer">Open &amp; print</a><a className="id-download-action" href={cardPath(card.id,format,true)} referrerPolicy="no-referrer">Download</a></div></div>
      <p className="id-private-note">Keep your card and QR code private.</p>
    </section>
  </section>
}
