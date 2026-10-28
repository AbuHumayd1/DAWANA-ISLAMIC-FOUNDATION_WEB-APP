import { useEffect, useState } from 'react'
import { getOperationsData, postOperationsData } from '../services/operationsApi'
import { financePath, financeSections, naira, entryActions, receivedKobo, recentFinanceRows } from '../services/finance'
import './Finance.css'

const reports = ['registration', 'income', 'expenses', 'budgets', 'reconciliation', 'summary']
export default function Finance() {
  const [editions, setEditions] = useState([]), [edition, setEdition] = useState('')
  const [data, setData] = useState(null), [tab, setTab] = useState('Overview')
  const [filters, setFilters] = useState({}), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [revision, refresh] = useState(0), [detail, setDetail] = useState(null), [notice, setNotice] = useState('')
  const [metadataRevision, refreshMetadata] = useState(0), [metadataLoading, setMetadataLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    getOperationsData('/finance/?metadata=1', { signal: controller.signal }).then(result => {
      setEditions(result.editions || []); setEdition(String(result.editions?.[0]?.id || ''))
    }).catch(e => { if (e.name !== 'AbortError') setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setMetadataLoading(false) })
    return () => controller.abort()
  }, [metadataRevision])
  useEffect(() => {
    if (!edition) return
    const controller = new AbortController()
    getOperationsData(financePath(edition, filters), { signal: controller.signal }).then(result => { setData(result); setError(''); setDetail(null) })
      .catch(e => { if (e.name !== 'AbortError') setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [edition, filters, revision])
  function reload() {
    setData(null); setDetail(null); setError('')
    if (!edition) { setMetadataLoading(true); refreshMetadata(r => r + 1) }
    else refresh(r => r + 1)
  }
  function changeFilters(next) { setData(null); setDetail(null); setError(''); setFilters(next) }
  async function mutate(payload) {
    if (busy || !window.confirm('Confirm this financial action? Original records and audit history will be retained.')) return
    setBusy(true); setError(''); setNotice('')
    try { await postOperationsData(financePath(edition), payload); setNotice('Financial action recorded.'); reload() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  function submit(event, action) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    mutate({ action, ...values })
  }
  async function exportReport(report) {
    setBusy(true); setError('')
    try {
      const base = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
      const response = await fetch(`${base}/dic/operations${financePath(edition, { ...filters, export: report })}`, { credentials: 'include' })
      if (!response.ok) { const body = await response.json(); throw new Error(body.detail || 'Finance export failed.') }
      const url = URL.createObjectURL(await response.blob()), link = document.createElement('a')
      link.href = url; link.download = `dic-finance-${report}.csv`; link.click(); URL.revokeObjectURL(url)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function attachReceipt(event) {
    event.preventDefault()
    if (busy || !detail || !window.confirm('Attach this private supporting receipt to the draft?')) return
    setBusy(true); setError('')
    try {
      const form = new FormData(event.currentTarget)
      form.set('action', 'receipt'); form.set('id', detail.id); form.set('version', String(detail.version))
      const base = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
      const csrf = await fetch(`${base}/dic/operations/auth/csrf/`, { credentials: 'include', cache: 'no-store' })
      if (!csrf.ok) throw new Error('Could not establish a secure receipt upload.')
      const token = await csrf.json()
      const response = await fetch(`${base}/dic/operations${financePath(edition)}`, { method: 'POST', credentials: 'include', headers: { 'X-CSRFToken': token.csrfToken }, body: form })
      if (!response.ok) { const body = await response.json(); throw new Error(body.detail || 'Receipt upload failed.') }
      reload(); setNotice('Private receipt attached.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const permissions = data?.permissions || {}, summary = data?.summary || {}
  const kind = tab === 'Other income' ? 'income' : 'expense'
  return <div className="finance-page">
    <header><span className="ops-eyebrow">DIC OPERATIONS</span><h1>Finance</h1><p>Money received, money spent and what remains.</p></header>
    <label>Camp edition<select value={edition} onChange={e => { setData(null); setDetail(null); setError(''); setNotice(''); setEdition(e.target.value); setFilters({}) }}><option value="">Choose edition</option>{editions.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
    <details className="finance-tools"><summary>More Finance tools</summary><nav aria-label="Finance sections">{financeSections.map(section => <button type="button" key={section} aria-current={tab === section ? 'page' : undefined} onClick={() => { setTab(section); setDetail(null) }}>{section}</button>)}</nav></details>
    <details className="finance-tools"><summary>Search and filters{Object.keys(filters).some(key => key !== 'page') ? ' (filters active)' : ''}</summary><form key={edition} className="finance-filters" onSubmit={e => { e.preventDefault(); changeFilters(Object.fromEntries([...new FormData(e.currentTarget)].filter(([, v]) => v))) }}>
      <label>Search reference or title<input name="q" /></label><label>From<input name="date_from" type="date" /></label><label>Through<input name="date_to" type="date" /></label>
      <label>Record status<input name="status" placeholder="e.g. successful, submitted, paid" /></label>
      <label>Booking payment status<select name="payment_status"><option value="">All</option>{['pending', 'paid', 'failed', 'refunded'].map(status => <option key={status}>{status}</option>)}</select></label>
      <label>Registration category<select name="category"><option value="">All</option>{data?.registration_categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label>Finance category<select name="finance_category"><option value="">All</option>{data?.categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <button disabled={busy || !edition}>Apply filters</button><button type="button" onClick={() => changeFilters({})}>Clear filters</button>
    </form></details>
    {error && <div role="alert" className="ops-error">{error} <button type="button" disabled={busy} onClick={reload}>Retry</button></div>}
    {notice && <p role="status">{notice}</p>}{(metadataLoading || busy || (edition && !data && !error)) && <p role="status">Loading Finance…</p>}
    {!metadataLoading && !error && !editions.length && <p role="status">No camp editions are available.</p>}
    {data && <><details className="finance-tools"><summary>How these figures work</summary><p className="finance-note">{data.semantics}</p></details>
      {tab !== 'Overview' && <><button type="button" onClick={() => { setTab('Overview'); setDetail(null) }}>Back to overview</button><h2>{tab}</h2></>}
      {tab === 'Overview' && <FinanceOverview summary={summary} permissions={permissions} payments={data.payments} entries={data.entries} busy={busy} onAction={next => { setTab(next); changeFilters({}); setNotice('') }} onDetail={setDetail} />}
      {!permissions.view_details && tab !== 'Overview' && <p>Finance transaction-detail permission is required.</p>}
      {permissions.view_details && <>
        {['Registration revenue', 'Reconciliation'].includes(tab) && <FinanceTable rows={data.payments} columns={['reference', 'date', 'status', 'payment_status', 'amount_kobo', 'verified_kobo', 'exception', 'reconciliation']} onDetail={setDetail} />}
        {['Other income', 'Expenses'].includes(tab) && <>
          {permissions[kind === 'income' ? 'record_income' : 'submit_expense'] && <FinanceEntryForm kind={kind} categories={data.categories} busy={busy} onSubmit={e => submit(e, 'create')} />}
          <FinanceTable rows={data.entries.filter(e => e.kind === kind)} columns={['title', 'category', 'date', 'amount_kobo', 'status', 'reference']} onDetail={setDetail} />
        </>}
        {detail && <section className="finance-detail"><h2>Financial record detail</h2><dl>{Object.entries(detail).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{key.endsWith('_kobo') ? naira(value) : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value ?? '')}</dd></div>)}</dl>{detail.kind && <><label>Action justification<input id="finance-action-reason" /></label>{entryActions(detail, permissions).map(action => <button disabled={busy} key={action} onClick={() => mutate({ action, id: detail.id, version: detail.version, reason: document.getElementById('finance-action-reason').value })}>{action === 'pay' ? 'Confirm money paid' : action}</button>)}</>}{detail.has_receipt && <a href={`${(import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')}/dic/operations${financePath(edition, { receipt: detail.id })}`}>Download private receipt</a>}{detail.kind && detail.status === 'draft' && permissions[detail.kind === 'income' ? 'record_income' : 'submit_expense'] && <form onSubmit={attachReceipt}><label>Private receipt (PDF, PNG, JPEG; up to 2 MB)<input name="receipt" type="file" accept="application/pdf,image/png,image/jpeg" required /></label><Fields names={['reason']} /><button disabled={busy}>Attach receipt</button></form>}<button onClick={() => setDetail(null)}>Close detail</button></section>}
        {tab === 'Budgets' && <><p>Budget revisions and actual spending are edition-wide; transaction filters do not change these balances.</p><FinanceTable rows={data.budgets} columns={['category', 'amount_kobo', 'actual_kobo', 'remaining_kobo', 'utilisation_percent', 'over_budget']} onDetail={setDetail} /><h2>Revision history</h2><FinanceTable rows={data.budget_history} columns={['category', 'amount_kobo', 'approved_by', 'date', 'reason']} onDetail={setDetail} />{permissions.manage_budget && <><form className="finance-form" onSubmit={e => submit(e, 'budget')}><h2>Approve revised category allocation</h2><label>Expense category<select required name="category"><option value="">Choose category</option>{data.categories.filter(c => c.kind === 'expense' && c.active).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><Fields names={['amount', 'reason']} /><button disabled={busy}>Record approved revision</button></form><form className="finance-form" onSubmit={e => submit(e, 'category')}><h2>Add authorised finance category</h2><Fields names={['name', 'reason']} /><label>Type<select name="kind"><option value="income">Income</option><option value="expense">Expense / budget</option></select></label><button disabled={busy}>Add category</button></form></>}</>}
        {tab === 'Reconciliation' && permissions.reconcile && <form className="finance-form" onSubmit={e => submit(e, 'reconcile')}><h2>Record provider evidence</h2><label>Payment attempt<select required name="attempt"><option value="">Choose attempt</option>{data.payments.map(p => <option key={p.id} value={p.id}>{p.reference}</option>)}</select></label><label>Outcome<select name="outcome">{['matched', 'exception', 'refund', 'reversal'].map(s => <option key={s}>{s}</option>)}</select></label><Fields names={['amount', 'reference', 'evidence', 'reason']} /><p>This records evidence only. It cannot verify a payment or change registration eligibility.</p><button disabled={busy}>Record reconciliation evidence</button></form>}
        {tab === 'Reports' && (permissions.export ? <><h2>Finance exports</h2><p>Excel-compatible UTF-8 CSV. Monetary columns ending in kobo are exact minor currency units.</p>{reports.map(report => <span key={report}><button disabled={busy} onClick={() => exportReport(report)}>Export {report}</button><a target="_blank" rel="noopener noreferrer" href={(import.meta.env?.VITE_API_BASE_URL||'/api/v1').replace(/\/$/,'')+'/dic/operations'+financePath(edition,{...filters,export:report,output:'print'})}>Print {report}</a></span>)}</> : <p>Finance export permission is required.</p>)}
        {['Registration revenue', 'Other income', 'Expenses', 'Reconciliation', 'Budgets'].includes(tab) && <div className="finance-pagination"><button disabled={busy || (data.page || 1) <= 1} onClick={() => changeFilters({ ...filters, page: String((data.page || 1) - 1) })}>Previous</button><span>Page {data.page || 1} · Up to 50 records per list</span><button disabled={busy || !Object.values(data.counts || {}).some(count => count > (data.page || 1) * 50)} onClick={() => changeFilters({ ...filters, page: String((data.page || 1) + 1) })}>Next</button></div>}
      </>}
    </>}
  </div>
}

export function FinanceOverview({ summary, permissions, payments = [], entries = [], busy = false, onAction, onDetail }) {
  const rows = permissions.view_details ? recentFinanceRows(payments, entries) : []
  return <section aria-label="Finance overview">
    <div className="finance-metrics">{[
      ['Money Received', receivedKobo(summary)], ['Money Spent', summary.expenditure_kobo],
      ['Recorded Net Position', summary.net_position_kobo],
    ].map(([label, value]) => <article key={label}><span>{label}</span><strong>{naira(value)}</strong></article>)}</div>
    <p>Online registration payments appear automatically once verified. Money Received also includes approved other income. Money Spent includes paid expenses only.</p>
    <p className="finance-note">These figures follow the selected filters. Recorded Net Position is recorded income minus paid expenses, not a reconciled bank balance or available operating balance.</p>
    <div className="finance-quick-actions">
      <button type="button" disabled={busy || !permissions.view_details || !permissions.record_income} onClick={() => onAction('Other income')}>Add Money In</button>
      <button type="button" disabled={busy || !permissions.view_details || !permissions.submit_expense} onClick={() => onAction('Expenses')}>Record Expense</button>
    </div>
    {(!permissions.view_details || !permissions.record_income || !permissions.submit_expense) && <p className="finance-note">Entry actions require transaction-detail access and the relevant recording permission.</p>}
    <h2>Recent transactions</h2>
    {permissions.view_details ? <>
      <p className="finance-note">Up to 10 records, newest dates first, from the loaded transaction pages. Open the relevant Finance section to browse more. Drafts and unpaid expenses are excluded from the totals; online amounts show verified receipts after adjustments.</p>
      <FinanceTable rows={rows} columns={['source', 'amount_kobo', 'date', 'status']} onDetail={row => onDetail(row.record)} />
    </> : <p>Transaction-detail permission is required to see recent transactions.</p>}
    <details className="finance-tools"><summary>Approvals, budgets and payment checks</summary>
      <p>Approved but unpaid: {naira(summary.approved_unpaid_kobo)}. Approved budget: {naira(summary.approved_budget_kobo)}. Budget remaining: {naira(summary.remaining_budget_kobo)}.</p>
      <p>Gross verified collections: {naira(summary.gross_verified_collections_kobo)}. Recorded refunds/reversals: {naira(summary.recorded_adjustments_kobo)}. Net verified collections: {naira(summary.net_verified_collections_kobo)}. Available operating balance: {naira(summary.available_operating_balance_kobo)}.</p>
      <p>Pending online payments: {summary.pending_attempts} · Failed: {summary.failed_attempts} · Exceptions: {summary.exceptions}. Review these in Registration revenue or Reconciliation under More Finance tools.</p>
    </details>
  </section>
}

export function FinanceEntryForm({ kind, categories, busy, onSubmit }) {
  const available = categories.filter(category => category.active && category.kind === kind)
  return <form onSubmit={onSubmit} className="finance-form" aria-label={kind === 'income' ? 'Add Money In' : 'Record Expense'}>
    <h2>{kind === 'income' ? 'Add Money In' : 'Record Expense'}</h2>
    <p>{kind === 'income' ? 'For money received outside online registration. Online payments are added automatically; do not enter them again.' : 'Save an expense draft for review. Saving or approval does not mark it paid.'} The totals change only after the existing approval or payment steps.</p>
    <label>Category<select name="category" required><option value="">Choose category</option>{available.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
    <Fields names={['title', 'amount', 'date', 'method', 'reference', 'reason']} />
    <details className="finance-entry-extras"><summary>Extra details and payment evidence (optional)</summary><Fields names={['payee', 'responsible', 'description', 'evidence']} /><p>Payment confirmation needs an evidence reference or a private receipt. A receipt can be attached while the entry is a draft.</p></details>
    {!available.length && <p>An authorized budget manager must add an appropriate category before you can save.</p>}
    <button disabled={busy || !available.length}>Save draft for review</button>
  </form>
}

const fieldLabels = { title: 'What is this for?', amount: 'Amount (NGN)', date: 'Date', method: 'Payment method',
  reference: 'Payment or document reference', reason: 'Reason for this record', payee: 'Paid to / received from',
  responsible: 'Responsible official', description: 'Additional notes', evidence: 'Payment evidence reference', name: 'Category name' }
function Fields({ names }) {
  return names.map(name => <label key={name}>{fieldLabels[name] || name.replaceAll('_', ' ')}{['description', 'evidence', 'reason'].includes(name) ? <textarea name={name} required={name === 'reason'} maxLength="10000" /> : <input name={name} required={['title', 'name', 'amount', 'date', 'method', 'reference'].includes(name)} type={name === 'date' ? 'date' : name === 'amount' ? 'number' : 'text'} min={name === 'amount' ? '0.01' : undefined} step={name === 'amount' ? '0.01' : undefined} maxLength={name === 'method' ? 40 : name === 'reference' ? 100 : 160} />}</label>)
}
function FinanceTable({ rows, columns, onDetail }) {
  if (!rows.length) return <p>No matching records. No financial data has been invented.</p>
  return <div className="finance-table" tabIndex="0" role="region" aria-label="Financial records"><table><thead><tr>{columns.map(c => <th key={c}>{c.replaceAll('_', ' ')}</th>)}<th>Detail</th></tr></thead><tbody>{rows.map((row, index) => <tr key={row.id || index}>{columns.map(c => <td key={c}>{c.endsWith('_kobo') ? naira(row[c]) : String(row[c] ?? '')}</td>)}<td><button onClick={() => onDetail(row)}>View</button></td></tr>)}</tbody></table></div>
}
