import { useEffect, useState } from 'react'
import { downloadIDBatch, getOperationsData, postOperationsData } from '../services/operationsApi'
import { HelpDetails } from '../components/operations/OperationsControls'

export default function ParticipantIDPrinting() {
  const [data, setData] = useState(null)
  const [selected, setSelected] = useState([])
  const [house, setHouse] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('all')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const refresh = () => getOperationsData('/id-printing/').then(setData)
  useEffect(() => { let live = true; getOperationsData('/id-printing/').then(value => { if (live) setData(value) }).catch(e => { if (live) setError(e.message) }); return () => { live = false } }, [])
  const rows = (data?.results || []).filter(row => (!house || row.house === house) && (!category || row.category === category) && (status !== 'unprinted' || !row.printed) && (status !== 'unexported' || !row.exported))
  const run = async action => {
    setBusy(true); setError('')
    try { await action(); await refresh() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="ops-panel ops-id-printing">
    <div className="ops-page-heading"><div><h1>ID Card Printing</h1><p>Select participants and download their ID cards.</p></div></div>
    <HelpDetails label="Printing help"><p>Only eligible participants with active, issued IDs are listed. Four 90 × 130 mm badges fit on each A4 sheet. Print at actual size (100%). A download records an export; confirm physical printing only after the batch has been printed.</p></HelpDetails>
    {error && <p role="alert">{error}</p>}
    {!data ? <p>Loading participant directory…</p> : <>
      <div className="ops-filters ops-primary-filters">
        <label className="ops-filter">House <select value={house} onChange={e => { setHouse(e.target.value); setSelected([]) }}><option value="">All houses</option>{[...new Set(data.results.map(r => r.house))].map(h => <option key={h}>{h}</option>)}</select></label>
        <label className="ops-filter">Category <select value={category} onChange={e => { setCategory(e.target.value); setSelected([]) }}><option value="">All categories</option>{[...new Set(data.results.map(r => r.category))].map(c => <option key={c}>{c}</option>)}</select></label>
        <label className="ops-filter">Print status <select value={status} onChange={e => { setStatus(e.target.value); setSelected([]) }}><option value="all">All, including reprints</option><option value="unprinted">Current card not confirmed printed</option><option value="unexported">Current card not exported</option></select></label>
      </div>
      <p>{rows.length} eligible participants · {selected.length} selected · {Math.ceil(selected.length / 4)} A4 sheets</p>
      <div className="ops-print-actions"><button className="ops-button ops-button-secondary" disabled={busy} onClick={() => setSelected(rows.map(r => r.id))}>Select all shown</button>{' '}
      <button className="ops-button ops-button-secondary" disabled={busy} onClick={() => setSelected([])}>Clear selection</button>{' '}
      <button className="ops-button ops-button-primary" disabled={busy || !selected.length} onClick={() => run(async () => { await downloadIDBatch(selected); setSelected([]) })}>Download Bulk ID Cards (A4 PDF)</button></div>
      {!rows.length && <div className="ops-empty"><h3>No ID cards to show</h3><p>Try another filter. Eligible, issued cards will appear here.</p></div>}
      <div className="ops-table-wrap"><table className="ops-table"><thead><tr><th>Select</th><th>Participant</th><th>ID number</th><th>House</th><th>Category</th><th>Status</th></tr></thead><tbody>{rows.map(r => <tr key={r.id}><td><input type="checkbox" aria-label={`Select ${r.name}`} disabled={busy} checked={selected.includes(r.id)} onChange={e => setSelected(e.target.checked ? [...selected, r.id] : selected.filter(id => id !== r.id))} /></td><td>{r.name}</td><td>{r.participant_number}</td><td>{r.house}</td><td>{r.category}</td><td>V{r.version}: {r.printed ? 'Confirmed printed' : r.exported ? 'Exported' : 'Ready'}{r.legacy_history && <small> · Earlier history has unknown credential version</small>}{!r.printed && r.previously_printed && <small> · Earlier badge confirmed printed</small>}</td></tr>)}</tbody></table></div>
      <h2>Printing history</h2>
      {!data.history.length && <p className="ops-small-note">No ID batches have been exported yet.</p>}
      <ul>{data.history.map(event => <li key={`${event.id}-${event.action}`}>{event.action.endsWith('_printed') ? 'Confirmed printed' : 'Exported'} · {event.card_count} cards · {event.actor} · {new Date(event.timestamp).toLocaleString()} · Batch {event.id}
        <details><summary>Participant IDs and credential versions</summary>{event.cards ? event.cards.map(card => `${card.participant_number} (V${card.version})`).join(', ') : `${event.participant_numbers.join(', ')} — credential version unknown`}</details>
        {event.action.endsWith('_exported') && !data.history.some(e => e.id === event.id && e.action.endsWith('_printed')) && <button className="ops-button ops-button-secondary" disabled={busy} onClick={() => run(() => postOperationsData(`/id-printing/${event.id}/printed/`, {}))}>Confirm physically printed</button>}
      </li>)}</ul>
    </>}
  </section>
}
