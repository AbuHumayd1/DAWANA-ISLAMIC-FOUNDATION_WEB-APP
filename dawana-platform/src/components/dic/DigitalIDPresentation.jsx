import { useState } from 'react'
import { participantCardPath, staffCardPath } from '../../services/participantIdentity'
import './DigitalIDPresentation.css'

export default function DigitalIDPresentation({ card, onClose, staff = false }) {
  const [format, setFormat] = useState('pvc')
  const cardPath = staff ? staffCardPath : participantCardPath
  return <section className="participant-id-view id-presentation" aria-label="My Digital ID">
    <header className="id-presentation-heading"><div><span className="id-eyebrow">YOUR CAMP IDENTITY</span><h1>My Digital ID</h1><p>{card.name}</p><span className="participant-id-number">{card.participant_number}</span></div><button type="button" className="id-back" onClick={onClose}>← Back to participants</button></header>
    <div className="id-presentation-grid"><section className="id-preview-panel" aria-label="Issued card preview">
      <div className="id-format-tabs" role="group" aria-label="Preview format">{[['pvc','PVC card'],['a6','A6 badge']].map(([key,label]) => <button type="button" key={key} aria-pressed={format === key} onClick={() => setFormat(key)}>{label}</button>)}</div>
      <div className="id-secure-preview"><span className="id-eyebrow">ISSUED DIGITAL ID</span><h2>{format === 'pvc' ? 'PVC card preview' : 'A6 badge preview'}</h2><p>View your actual issued card and QR code on its protected preview page.</p><a className="id-primary-action" href={cardPath(card.id,format)} referrerPolicy="no-referrer">Open secure {format === 'pvc' ? 'PVC card' : 'A6 badge'} preview</a></div>
      <p className="id-private-note">Keep your card and QR code private. The secured preview opens as a separate page to preserve its protection against embedding.</p>
    </section><aside className="id-action-panel" aria-label="Card formats and downloads"><h2>Your card, ready to use</h2><p>Choose a format to open, print or save.</p>
      <section className="id-action-group"><h3>Print-ready cards</h3>{[['pvc','PVC card'],['a6','A6 badge']].map(([key,label]) => <div className="id-format-row" key={key}><strong>{label}</strong><a href={cardPath(card.id,key)}>Open / print</a><a href={cardPath(card.id,key,true)}>Download HTML</a></div>)}</section>
      <section className="id-action-group"><h3>PDF badge</h3><p>Portrait format for printing or saving.</p><a className="id-primary-action" href={cardPath(card.id,'portrait',true)}>Download portrait badge PDF</a></section>
    </aside></div>
  </section>
}
