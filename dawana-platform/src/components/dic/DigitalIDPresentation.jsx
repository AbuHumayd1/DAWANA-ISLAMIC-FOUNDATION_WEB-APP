import { useState } from 'react'
import { participantCardPath, staffCardPath } from '../../services/participantIdentity'
import './DigitalIDPresentation.css'

export default function DigitalIDPresentation({ card, onClose, staff = false }) {
  const [format, setFormat] = useState('pvc')
  const cardPath = staff ? staffCardPath : participantCardPath
  return <section className="participant-id-view id-presentation" aria-label="My Digital ID">
    <header className="id-presentation-heading"><div><h1>{staff ? 'Participant Digital ID' : 'My Digital ID'}</h1><p>{card.name}</p><span className="participant-id-number">{card.participant_number}</span></div><button type="button" className="id-back" onClick={onClose}>← Back to participants</button></header>
    <div className="id-presentation-grid"><section className="id-preview-panel" aria-label="Issued card preview">
      <div className="id-format-tabs" role="group" aria-label="Preview format">{[['pvc','PVC card'],['a6','A6 badge']].map(([key,label]) => <button type="button" key={key} aria-pressed={format === key} onClick={() => setFormat(key)}>{label}</button>)}</div>
      <div className="id-secure-preview"><h2>{format === 'pvc' ? 'PVC Card' : 'A6 Badge'}</h2><p>Open your issued card to preview or print it.</p><a className="id-primary-action" href={cardPath(card.id,format)} referrerPolicy="no-referrer">Preview {format === 'pvc' ? 'PVC Card' : 'A6 Badge'}</a></div>
      <p className="id-private-note">Keep your card and QR code private.</p>
    </section><aside className="id-action-panel" aria-label="Card formats and downloads"><h2>Your card, ready to use</h2><p>Choose a format to open, print or save.</p>
      <section className="id-action-group"><h3>Card formats</h3>{[['pvc','PVC Card'],['a6','A6 Badge']].map(([key,label]) => <div className="id-format-row" key={key}><strong>{label}</strong><a href={cardPath(card.id,key)}>Open &amp; print</a><a href={cardPath(card.id,key,true)}>Download card</a></div>)}</section>
      <section className="id-action-group"><h3>PDF Badge</h3><div className="id-format-row"><a href={cardPath(card.id,'portrait')}>Preview &amp; print PDF</a><a href={cardPath(card.id,'portrait',true)}>Download PDF</a></div></section>
    </aside></div>
  </section>
}
