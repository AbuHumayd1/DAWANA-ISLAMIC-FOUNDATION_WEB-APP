import { visibleOperationsNavigation } from '../services/operationsNavigation'
import { useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Outlet, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import {
  downloadOperationsReport,
  getOperationsData,
  getOperationsUser,
  signIn,
  signOut,
} from '../services/operationsApi'
import './Operations.css'
import AppearanceControls from '../components/layout/AppearanceControls'
import StaffParticipantIDs from './StaffParticipantIDs'



const iconPaths = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  clipboard: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4.5h6M9 9h6M9 13h6M9 17h3" /></>,
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM20 8v6m3-3h-6" /></>,
  card: <><rect x="2.5" y="5" width="19" height="14" rx="2" /><path d="M3 10h18M7 15h4" /></>,
  home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-6v-7h-4v7H4a1 1 0 0 1-1-1z" /></>,
  file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h8" /></>,
  activity: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
  logout: <><path d="M10 17l5-5-5-5M15 12H3" /><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" /></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  alert: <><path d="M10.3 3.9 2.5 18a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4m0 4h.01" /></>,
}

function Icon({ name, className = '' }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconPaths[name]}</svg>
}

function formatNumber(value) {
  return new Intl.NumberFormat('en-NG').format(value || 0)
}

function formatDate(value, options = {}) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', ...options }).format(new Date(value))
}

function statusLabel(value) {
  return String(value || 'unknown').replaceAll('_', ' ')
}

function StatusPill({ value, positive = false }) {
  const normalized = String(value || '').toLowerCase()
  const tone = positive || ['paid', 'successful', 'confirmed', 'allocated', 'verified'].includes(normalized)
    ? 'success'
    : ['failed', 'cancelled', 'amount mismatch', 'reconciliation required', 'reconcile'].includes(normalized)
      ? 'danger'
      : ['pending', 'submitted', 'repricing required', 'not verified'].includes(normalized)
        ? 'warning'
        : 'neutral'
  return <span className={`ops-pill ops-pill-${tone}`}>{statusLabel(value)}</span>
}

function LoadingState({ rows = 4 }) {
  return <div className="ops-skeleton-list" aria-label="Loading data" aria-busy="true">{Array.from({ length: rows }, (_, index) => <div className="ops-skeleton" key={index} />)}</div>
}

function EmptyState({ title = 'No records to show', detail = 'New activity will appear here when it is available.' }) {
  return <div className="ops-empty"><span className="ops-empty-mark"><Icon name="file" /></span><h3>{title}</h3><p>{detail}</p></div>
}

function ErrorState({ error, onRetry }) {
  return <div className="ops-error" role="alert"><Icon name="alert" /><div><strong>We couldn’t load this information.</strong><p>{error?.message || 'Please try again.'}</p></div>{onRetry && <button className="ops-button ops-button-secondary" onClick={onRetry}>Try again</button>}</div>
}

function useData(path) {
  const [state, setState] = useState({ path: null, data: null, error: null })
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let live = true
    getOperationsData(path)
      .then((data) => { if (live) setState({ path, data, error: null }) })
      .catch((error) => { if (live) setState({ path, data: null, error }) })
    return () => { live = false }
  }, [path, refresh])
  return {
    ...state,
    loading: state.path !== path,
    data: state.path === path ? state.data : null,
    error: state.path === path ? state.error : null,
    retry: () => setRefresh((current) => current + 1),
  }
}

function Operations() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    const expire = () => {
      setUser(null)
      setError('Your session expired. Please sign in again.')
    }
    window.addEventListener('operations-session-expired', expire)
    return () => window.removeEventListener('operations-session-expired', expire)
  }, [])

  useEffect(() => {
    let live = true
    getOperationsUser()
      .then((profile) => { if (live) setUser(profile) })
      .catch(() => { if (live) setUser(null) })
      .finally(() => { if (live) setChecking(false) })
    return () => { live = false }
  }, [])

  const handleLogin = async (username, password) => {
    setError(null)
    try {
      const profile = await signIn(username, password)
      setUser(profile)
    } catch (loginError) {
      setError(loginError.message)
    }
  }

  const handleLogout = async () => {
    try {
      await signOut()
      setUser(null)
      navigate('/dic/operations', { replace: true })
    } catch (logoutError) {
      setError(logoutError.message)
    }
  }

  if (checking) return <div className="ops-full-state"><div className="ops-loading-mark" /><p>Securing your operations workspace…</p></div>
  if (!user) return <LoginPage onSubmit={handleLogin} error={error} />

  return (
    <Routes>
      <Route element={<OperationsShell user={user} onLogout={handleLogout} />}>
        <Route index element={<DashboardPage />} />
        <Route path="registrations" element={<RegistrationListPage />} />
        <Route path="registrations/:publicId" element={<RegistrationDetailPage />} />
        <Route path="participants" element={<ParticipantListPage />} />
        <Route path="participant-ids" element={user.permissions.ids ? <StaffParticipantIDs user={user} /> : <EmptyState title="Participant ID lookup permission required" />} />
        <Route path="participants/:participantId" element={<ParticipantDetailPage user={user} />} />
        <Route path="payments" element={user.permissions.finance ? <PaymentsPage /> : <EmptyState title="Finance permission required" />} />
        <Route path="houses" element={<HousesPage />} />
        <Route path="reports" element={user.permissions.export_reports ? <ReportsPage user={user} /> : <EmptyState title="Report export permission required" />} />
        <Route path="activity" element={user.permissions.audit ? <ActivityPage /> : <EmptyState title="Audit permission required" />} />
        <Route path="*" element={<DashboardPage />} />
      </Route>
    </Routes>
  )
}

function LoginPage({ onSubmit, error }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const submit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setFormError('')
    await onSubmit(username, password)
      .catch((submitError) => setFormError(submitError.message))
      .finally(() => setSubmitting(false))
  }
  return (
    <main className="ops-login-page">
      <AppearanceControls />
      <section className="ops-login-card">
        <BrandLockup />
        <div className="ops-login-heading"><span className="ops-eyebrow">Private workspace</span><h1>DIC Operations</h1><p>Sign in with your Dawana staff account to continue.</p></div>
        <form className="ops-login-form" onSubmit={submit}>
          <label>Username or email<input autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {(error || formError) && <p className="ops-form-error" role="alert">{formError || error}</p>}
          <button className="ops-button ops-button-primary" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in securely'}<Icon name="arrow" /></button>
        </form>
        <p className="ops-login-footnote">Access is managed by your system administrator. This portal does not store your password in the browser.</p>
      </section>
    </main>
  )
}

function BrandLockup() {
  return <div className="ops-brand"><img src="https://lh3.googleusercontent.com/aida-public/AB6AXuDCGXJAzZ-UcWviePlSOQS31EaODKnU6pYnNVPZAIb_b-9lqS8LhiVGxnepujEXC4rbBB7dpPXi16s19Sdppz9cRMR-W6-5qoOvKHiyjSLG90SoGGcrEUpx4Z5RaWE6rdOWa_BsxPa57V9ULj-cq7v2VYn_NFMd7eHZVxCDZISlBx1os-S3z_3e7nhljVT48l6trWf8o2hKb0Xdd7Jp-2sNGkPBc-SPgyiJhCh1VyCyCxGmv53SBGIj-DCzsF4BNKzvzA" alt="" /><span><strong>Da&apos;wãnã</strong><small>ISLAMIC FOUNDATION</small></span></div>
}

function OperationsShell({ user, onLogout }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
    const toggle = document.querySelector('.ops-menu-toggle')
    if (toggle?.getAttribute('aria-expanded') === 'true') toggle.click()
  }, [location.pathname])
  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        document.querySelector('.ops-menu-toggle')?.focus()
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [])
  const visibleNavigation = visibleOperationsNavigation(user)
  return (
    <div className="ops-app">
      <header className="ops-topbar">
        <button className="ops-menu-toggle" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}><Icon name="menu" /></button>
        <Link to="/dic/operations" className="ops-top-brand"><BrandLockup /></Link>
        <div className="ops-top-spacer" />
        <AppearanceControls />
        <span className="ops-edition-chip"><i /> Daarul Islam Camp 2026</span>
        {user.can_access_django_admin && <a className="ops-admin-link" href="/admin/">Django Admin</a>}
        <div className="ops-profile"><span className="ops-avatar">{user.display_name.slice(0, 1).toUpperCase()}</span><span className="ops-profile-copy"><strong>{user.display_name}</strong><small>{user.role}</small></span></div>
        <button className="ops-logout" onClick={onLogout} aria-label="Sign out"><Icon name="logout" /><span>Sign out</span></button>
      </header>
      <div className="ops-body">
        <aside className={`ops-sidebar ${menuOpen ? 'is-open' : ''}`}>
          <div className="ops-side-label">CAMP MANAGEMENT</div>
          <nav aria-label="Operations navigation">
            {visibleNavigation.map((item) => <NavLink key={item.to} end={item.to === '/dic/operations'} to={item.to} onClick={() => setMenuOpen(false)} className={({ isActive }) => `ops-nav-link ${isActive ? 'is-active' : ''}`}><Icon name={item.icon} /><span>{item.label}</span>{item.label === 'Activity' && <span className="ops-nav-lock">•</span>}</NavLink>)}
          </nav>
          <div className="ops-sidebar-footer"><span className="ops-live-dot" />Private staff portal<span>Only authorized staff can access this workspace.</span></div>
        </aside>
        <main className="ops-main"><Outlet /></main>
      </div>
    </div>
  )
}

function PageHeading({ eyebrow, title, description, action }) {
  return <div className="ops-page-heading"><div><span className="ops-eyebrow">{eyebrow}</span><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>
}

function MetricCard({ title, value, note, icon, to, tone = '' }) {
  const content = <><div className={`ops-metric-icon ${tone}`}><Icon name={icon} /></div><div className="ops-metric-copy"><span>{title}</span><strong>{formatNumber(value)}</strong><small>{note}</small></div>{to && <Icon name="arrow" className="ops-metric-arrow" />}</>
  return to ? <Link to={to} className="ops-metric-card">{content}</Link> : <article className="ops-metric-card">{content}</article>
}

function DashboardPage() {
  const [period, setPeriod] = useState('14')
  const { data, loading, error, retry } = useData(`/dashboard/?days=${period}`)
  if (loading) return <><PageHeading eyebrow="DIC 2026" title="Operations overview" description="A live view of registrations, payments and camp readiness." /><LoadingState rows={7} /></>
  if (error) return <><PageHeading eyebrow="DIC 2026" title="Operations overview" /><ErrorState error={error} onRetry={retry} /></>
  const metrics = data.metrics
  const edition = data.edition
  const paidRate = metrics.orders ? Math.round((metrics.verified_paid_orders / metrics.orders) * 100) : 0
  return (
    <>
      <PageHeading eyebrow={edition?.name || 'DIC Operations'} title="Operations overview" description="A clear picture of registrations, payment verification and camp readiness." action={<span className={`ops-registration-state state-${edition?.registration_status || 'draft'}`}><i /> Registration {statusLabel(edition?.registration_status || 'not configured')}</span>} />
      {edition && <div className="ops-edition-banner"><span className="ops-banner-mark"><Icon name="home" /></span><div><strong>{edition.name}</strong><span>{formatDate(edition.camp_start_date)} – {formatDate(edition.camp_end_date)} <b>·</b> {edition.venue}</span></div><span className="ops-edition-status">Registration closed</span></div>}
      <section className="ops-metric-grid" aria-label="Registration metrics">
        <MetricCard title="Registration orders" value={metrics.orders} note="Parent or guardian checkouts" icon="clipboard" to="/dic/operations/registrations" />
        <MetricCard title="Individual participants" value={metrics.participants} note="Participants across all orders" icon="users" tone="gold" to="/dic/operations/participants" />
        <MetricCard title="Verified paid orders" value={metrics.verified_paid_orders} note={`${paidRate}% of all orders`} icon="card" tone="green" to="/dic/operations/registrations?payment_status=paid" />
        <MetricCard title="Paid participants" value={metrics.verified_paid_participants} note="Payment verified by provider" icon="users" tone="green" to="/dic/operations/participants?payment_status=paid" />
        <MetricCard title="Pending / unpaid" value={metrics.pending_unpaid_orders} note="Orders awaiting payment" icon="card" tone="amber" to="/dic/operations/registrations?payment_status=pending" />
        <MetricCard title="Repricing required" value={metrics.requiring_repricing} note="Needs explicit updated-price acceptance" icon="activity" tone="amber" to="/dic/operations/registrations?requiring_repricing=true" />
        {metrics.reconciliation_cases !== null && <MetricCard title="Reconciliation cases" value={metrics.reconciliation_cases} note="Finance review required" icon="alert" tone="red" to="/dic/operations/payments?status=reconcile" />}
        <MetricCard title="Eligible, unallocated" value={metrics.eligible_unallocated_participants} note="Verified participants without a house" icon="home" tone="gold" to="/dic/operations/houses" />
      </section>
      <label className="ops-filter">Activity period <select value={period} onChange={(event) => setPeriod(event.target.value)}><option value="7">Last 7 days</option><option value="14">Last 14 days</option><option value="30">Last 30 days</option></select></label>
      <section className="ops-chart-grid">
        <article className="ops-panel ops-activity-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">LAST {period} DAYS</span><h2>Registration activity</h2></div><Link to="/dic/operations/registrations" className="ops-text-link">All registrations <Icon name="arrow" /></Link></div><ActivityChart rows={data.registration_activity} /></article>
        <article className="ops-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">EDITION BREAKDOWN</span><h2>Participants by category</h2></div></div><BarList rows={data.category_distribution.map((row) => ({ label: row.category_name_snapshot, value: row.participants }))} empty="Category details will appear once registrations begin." /></article>
        <article className="ops-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">VERIFICATION</span><h2>Payment status</h2></div></div><StatusDistribution rows={data.payment_distribution} total={metrics.orders} /></article>
        <article className="ops-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">CAMP READINESS</span><h2>House allocations</h2></div><Link to="/dic/operations/houses" className="ops-text-link">View houses <Icon name="arrow" /></Link></div><BarList rows={data.house_distribution.map((row) => ({ label: row.name, value: row.allocated_count, meta: row.capacity ? `of ${row.capacity}` : 'participants' }))} empty="No houses are configured for this edition." /></article>
      </section>
      <section className="ops-bottom-grid">
        <article className="ops-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">LATEST ACTIVITY</span><h2>Recent registrations</h2></div><Link to="/dic/operations/registrations" className="ops-text-link">View all <Icon name="arrow" /></Link></div><RegistrationTable rows={data.recent_registrations} compact /></article>
        <article className="ops-panel ops-attention-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">FOLLOW UP</span><h2>Needs attention</h2></div><span className="ops-attention-count">{data.attention.length}</span></div>{data.attention.length ? <ul className="ops-attention-list">{data.attention.slice(0, 6).map((item, index) => <li key={`${item.order_id}-${index}`}><span className="ops-attention-icon"><Icon name="alert" /></span><div><strong>{item.message}</strong><Link to={`/dic/operations/registrations/${item.order_id}`}>{item.reference}</Link></div><Icon name="arrow" className="ops-attention-arrow" /></li>)}</ul> : <EmptyState title="All clear for now" detail="No registrations currently need administrative attention." />}</article>
      </section>
      <footer className="ops-page-footer">Dawana Islamic Foundation <span>·</span> DIC 2026 Operations</footer>
    </>
  )
}

function ActivityChart({ rows }) {
  if (!rows.length) return <EmptyState title="No registration activity yet" detail="Activity will be charted here when registrations are received." />
  const maximum = Math.max(1, ...rows.map((row) => row.orders))
  return <div className="ops-activity-chart" role="img" aria-label="Registration order activity by day">{rows.map((row) => <div className="ops-activity-column" key={row.date} title={`${formatDate(row.date)}: ${row.orders} orders, ${row.participants} participants`}><div className="ops-activity-bars"><span style={{ height: `${Math.max(3, (row.orders / maximum) * 100)}%` }} /><i style={{ height: `${Math.max(3, (row.participants / Math.max(1, ...rows.map((entry) => entry.participants))) * 100)}%` }} /></div><small>{new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short' }).format(new Date(`${row.date}T12:00:00`))}</small></div>)}</div>
}

function BarList({ rows, empty }) {
  if (!rows.length) return <EmptyState title={empty} />
  const maximum = Math.max(1, ...rows.map((row) => row.value))
  return <div className="ops-bar-list">{rows.map((row) => <div className="ops-bar-row" key={row.label}><div className="ops-bar-label"><span>{row.label}</span><strong>{formatNumber(row.value)} <small>{row.meta}</small></strong></div><div className="ops-bar-track"><i style={{ width: `${Math.max(2, (row.value / maximum) * 100)}%` }} /></div></div>)}</div>
}

function StatusDistribution({ rows, total }) {
  if (!total) return <EmptyState title="No payments to report" detail="Payment status will be summarized after registrations arrive." />
  const colors = { paid: 'success', pending: 'warning', failed: 'danger', refunded: 'neutral' }
  return <div className="ops-status-list">{rows.map((row) => <div className="ops-status-row" key={row.payment_status}><span className={`ops-status-dot ${colors[row.payment_status] || 'neutral'}`} /><span>{statusLabel(row.payment_status)}</span><strong>{formatNumber(row.orders)}</strong><div className="ops-status-track"><i className={colors[row.payment_status] || 'neutral'} style={{ width: `${Math.max(2, (row.orders / total) * 100)}%` }} /></div></div>)}</div>
}

function useFilters(initial = {}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [filters, setFilters] = useState(() => ({
    ...initial,
    q: searchParams.get('q') || '',
    payment_status: searchParams.get('payment_status') || '',
    status: searchParams.get('status') || '',
    category: searchParams.get('category') || '',
    house: searchParams.get('house') || '',
    date_from: searchParams.get('date_from') || '',
    date_to: searchParams.get('date_to') || '',
    requiring_repricing: searchParams.get('requiring_repricing') || '',
  }))
  const [active, setActive] = useState(filters)
  const submit = (event) => {
    event?.preventDefault()
    const next = Object.fromEntries(Object.entries(filters).filter(([key, value]) => key !== 'page' && value))
    setFilters((current) => ({ ...current, page: '' }))
    setActive({ ...filters, page: '' })
    setSearchParams(next)
  }
  const setPage = (page) => {
    const next = { ...active, page: String(page) }
    setActive(next)
    setFilters(next)
    setSearchParams(Object.fromEntries(Object.entries(next).filter(([, value]) => value)))
  }
  const update = (name, value) => setFilters((current) => ({ ...current, [name]: value }))
  return { filters, active, update, submit, setPage }
}

function buildQuery(filters) {
  const query = new URLSearchParams(Object.fromEntries(Object.entries(filters).filter(([, value]) => value)))
  return query.size ? `?${query}` : ''
}

function SearchBar({ value, onChange, placeholder = 'Search by reference or name' }) {
  return <div className="ops-search"><Icon name="search" /><input aria-label="Search" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /><button type="submit">Search</button></div>
}

function DateFilter({ label, value, onChange }) {
  return <label className="ops-filter"><span>{label}</span><input type="date" value={value} onChange={(event) => onChange(event.target.value)} /></label>
}

function FilterSelect({ label, value, onChange, options }) {
  return <label className="ops-filter"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">All {label.toLowerCase()}</option>{options.map(([optionValue, text]) => <option value={optionValue} key={optionValue}>{text}</option>)}</select></label>
}

function RegistrationListPage() {
  const { filters, active, update, submit, setPage } = useFilters()
  const path = `/registrations/${buildQuery(active)}`
  const { data, loading, error, retry } = useData(path)
  const { data: filterOptions } = useData('/filters/')
  return <>
    <PageHeading eyebrow="DIC 2026" title="Registrations" description="Search parent orders, review payment status and follow up on quotes requiring repricing." />
    <section className="ops-panel ops-list-panel"><form className="ops-filterbar" onSubmit={submit}><SearchBar value={filters.q} onChange={(value) => update('q', value)} /><FilterSelect label="Payment status" value={filters.payment_status} onChange={(value) => update('payment_status', value)} options={ [['pending', 'Pending'], ['paid', 'Paid'], ['failed', 'Failed'], ['refunded', 'Refunded']] } /><FilterSelect label="Order status" value={filters.status} onChange={(value) => update('status', value)} options={ [['submitted', 'Submitted'], ['confirmed', 'Confirmed'], ['cancelled', 'Cancelled']] } /><FilterSelect label="Category" value={filters.category} onChange={(value) => update('category', value)} options={(filterOptions?.categories || []).map((item) => [item.id, item.name])} /><FilterSelect label="House" value={filters.house} onChange={(value) => update('house', value)} options={(filterOptions?.houses || []).map((item) => [item.id, item.name])} /><DateFilter label="From" value={filters.date_from} onChange={(value) => update('date_from', value)} /><DateFilter label="To" value={filters.date_to} onChange={(value) => update('date_to', value)} /><button className="ops-button ops-button-secondary" type="submit">Apply filters</button></form>
      {loading ? <LoadingState /> : error ? <ErrorState error={error} onRetry={retry} /> : <RegistrationTable rows={data.results} count={data.count} /> }
      {!loading && data?.pages > 1 && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}
    </section>
  </>
}

function RegistrationTable({ rows, count, compact = false }) {
  if (!rows?.length) return <EmptyState title="No registrations yet" detail="When a family completes a registration, the order and its participants will appear here." />
  return <div className="ops-table-wrap"><div className="ops-table-caption">{count !== undefined && <span>{formatNumber(count)} registration order{count === 1 ? '' : 's'}</span>}</div><table className="ops-table"><thead><tr><th>Registration</th><th>Date</th><th>Participants</th><th>Categories</th><th>Payment</th><th>Verification</th>{!compact && <th>Quoted total</th>}</tr></thead><tbody>{rows.map((row) => <tr key={row.id || row.reference}><td><Link className="ops-reference" to={`/dic/operations/registrations/${row.id || row.reference}`}>{(row.id || row.reference).slice(0, 13)}…</Link></td><td>{formatDate(row.created_at)}</td><td>{row.participant_count ?? row.participants ?? row.participants?.length ?? 0}</td><td>{row.categories?.join(', ') || '—'}</td><td><StatusPill value={row.payment_status} /></td><td><StatusPill value={row.verified_paid ? 'Verified' : 'Not verified'} positive={row.verified_paid} /></td>{!compact && <td>{row.quoted_total_ngn ? `₦${Number(row.quoted_total_ngn).toLocaleString('en-NG')}` : '—'}</td>}</tr>)}</tbody></table></div>
}

function Pagination({ page, pages, onChange }) {
  return <div className="ops-pagination"><span>Page {page} of {pages}</span><div><button disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button><button disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</button></div></div>
}

function RegistrationDetailPage() {
  const { publicId } = useParamsSafe()
  const { data, loading, error, retry } = useData(`/registrations/${publicId}/`)
  if (loading) return <><BackLink to="/dic/operations/registrations" label="Registrations" /><LoadingState rows={5} /></>
  if (error) return <><BackLink to="/dic/operations/registrations" label="Registrations" /><ErrorState error={error} onRetry={retry} /></>
  return <>
    <BackLink to="/dic/operations/registrations" label="Registrations" />
    <PageHeading eyebrow="Registration details" title={data.id} description={`Submitted ${formatDate(data.submitted_at)} · ${data.participant_count} individual participant${data.participant_count === 1 ? '' : 's'}`} action={<StatusPill value={data.verified_paid ? 'Verified paid' : data.payment_status} positive={data.verified_paid} />} />
    <div className="ops-detail-grid"><section className="ops-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">ORDER SUMMARY</span><h2>Registration status</h2></div></div><DetailRow label="Registration status" value={<StatusPill value={data.status} />} /><DetailRow label="Payment status" value={<StatusPill value={data.verified_paid ? 'Verified paid' : data.payment_status} positive={data.verified_paid} />} /><DetailRow label="Current quoted total" value={`₦${Number(data.quoted_total_ngn).toLocaleString('en-NG')}`} /><DetailRow label="Categories" value={data.categories.join(', ') || '—'} /><DetailRow label="Recovery" value={data.recovery_status} />{data.requires_repricing && <div className="ops-callout"><Icon name="alert" /><span>This unpaid order has an outdated quote. Staff cannot start payment using the old amount; the registrant must accept the updated quote.</span></div>}</section>
      {data.registrant && <section className="ops-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">PRIMARY REGISTRANT</span><h2>Guardian details</h2></div></div><DetailRow label="Name" value={data.registrant.name || '—'} /><DetailRow label="Email" value={data.registrant.email || '—'} /><DetailRow label="Phone" value={data.registrant.phone || '—'} /></section>}</div>
    <section className="ops-panel ops-detail-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">ORDER CONTENTS</span><h2>Participants</h2></div></div><div className="ops-participant-cards">{data.participants.map((person) => <article className="ops-person-card" key={person.id}><div className="ops-person-avatar">{person.name.slice(0, 1).toUpperCase()}</div><div className="ops-person-main"><Link to={`/dic/operations/participants/${person.id}`}><strong>{person.name}</strong></Link><span>{person.category} · ₦{Number(person.quoted_fee_ngn).toLocaleString('en-NG')}</span>{person.email && <small>{person.email} · {person.phone}</small>}</div><div className="ops-person-tags"><StatusPill value={person.verified_paid ? 'Verified paid' : 'Unpaid'} positive={person.verified_paid} />{person.allocations.map((allocation) => <span className="ops-house-tag" key={`${allocation.edition_year}-${allocation.house}`}>{allocation.house}</span>)}</div></article>)}</div></section>
    {data.pricing_revisions && <section className="ops-panel ops-detail-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">PRICE HISTORY</span><h2>Pricing revisions</h2></div></div>{data.pricing_revisions.length ? data.pricing_revisions.map((revision) => <DetailRow key={revision.revision} label={`Revision ${revision.revision} · ${formatDate(revision.created_at)}`} value={`₦${Number(revision.total_ngn).toLocaleString('en-NG')}${revision.accepted_at ? ' · accepted' : ''}`} />) : <EmptyState title="No pricing revisions" />}</section>}
    {data.payment_attempts && <section className="ops-panel ops-detail-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">FINANCE REVIEW</span><h2>Payment attempts</h2></div></div>{data.payment_attempts.length ? data.payment_attempts.map((attempt) => <DetailRow key={attempt.reference} label={`${attempt.reference} · ${statusLabel(attempt.status)}`} value={attempt.provider_paid_at ? formatDate(attempt.provider_paid_at, { timeStyle: 'short' }) : attempt.reconciliation_reason || 'Provider time unavailable'} />) : <EmptyState title="No payment attempts" />}</section>}
  </>
}

function useParamsSafe() {
  const location = useLocation()
  const parts = location.pathname.split('/')
  return { publicId: parts[parts.length - 1], participantId: parts[parts.length - 1] }
}

function BackLink({ to, label }) {
  return <Link to={to} className="ops-back-link">← {label}</Link>
}

function DetailRow({ label, value }) {
  return <div className="ops-detail-row"><span>{label}</span><strong>{value}</strong></div>
}

function ParticipantListPage() {
  const { filters, active, update, submit, setPage } = useFilters()
  const { data, loading, error, retry } = useData(`/participants/${buildQuery(active)}`)
  const { data: filterOptions } = useData('/filters/')
  if (loading) return <><PageHeading eyebrow="DIC 2026" title="Participants" description="A participant-focused directory across family registration orders." /><LoadingState rows={6} /></>
  return <>
    <PageHeading eyebrow="DIC 2026" title="Participants" description={`${formatNumber(data?.count)} individual participant records, separate from the number of registration orders.`} />
    <section className="ops-panel ops-list-panel"><form className="ops-filterbar" onSubmit={submit}><SearchBar value={filters.q} onChange={(value) => update('q', value)} placeholder="Search participant name" /><FilterSelect label="Payment status" value={filters.payment_status} onChange={(value) => update('payment_status', value)} options={ [['pending', 'Pending'], ['paid', 'Paid'], ['failed', 'Failed']] } /><FilterSelect label="Category" value={filters.category} onChange={(value) => update('category', value)} options={(filterOptions?.categories || []).map((item) => [item.id, item.name])} /><FilterSelect label="House" value={filters.house} onChange={(value) => update('house', value)} options={(filterOptions?.houses || []).map((item) => [item.id, item.name])} /><DateFilter label="From" value={filters.date_from} onChange={(value) => update('date_from', value)} /><DateFilter label="To" value={filters.date_to} onChange={(value) => update('date_to', value)} /><button className="ops-button ops-button-secondary" type="submit">Apply filters</button></form>{error ? <ErrorState error={error} onRetry={retry} /> : <><ParticipantTable rows={data?.results || []} count={data?.count} />{data?.pages > 1 && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}</>}</section>
  </>
}

function ParticipantTable({ rows, count }) {
  if (!rows.length) return <EmptyState title="No participants found" detail="Try adjusting your search or filters." />
  return <div className="ops-table-wrap"><div className="ops-table-caption">{formatNumber(count)} participants</div><table className="ops-table"><thead><tr><th>Participant</th><th>Registration reference</th><th>Category</th><th>Verified payment</th><th>House</th><th>Registration date</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><Link className="ops-reference" to={`/dic/operations/participants/${row.id}`}>{row.name}</Link></td><td><Link to={`/dic/operations/registrations/${row.registration_order_id}`} className="ops-muted-link">{row.registration_reference?.slice(0, 13)}…</Link></td><td>{row.category || '—'}</td><td><StatusPill value={row.verified_paid ? 'Verified paid' : row.payment_status || 'unpaid'} positive={row.verified_paid} /></td><td>{row.house || 'Unallocated'}</td><td>{formatDate(row.registration_date)}</td></tr>)}</tbody></table></div>
}

function ParticipantDetailPage({ user }) {
  const { participantId } = useParamsSafe()
  const { data, loading, error, retry } = useData(`/participants/${participantId}/`)
  if (loading) return <LoadingState rows={5} />
  if (error) return <ErrorState error={error} onRetry={retry} />
  return <>
    <BackLink to="/dic/operations/participants" label="Participants" />
    <PageHeading eyebrow="Participant profile" title={data.name} description={`Registration reference ${data.registration_reference || 'not available'}`} />
    <section className="ops-panel ops-detail-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">REGISTRATION</span><h2>Participant details</h2></div><StatusPill value={data.verified_paid ? 'Verified paid' : data.payment_status || 'unpaid'} positive={data.verified_paid} /></div><DetailRow label="Category" value={data.category || '—'} /><DetailRow label="House" value={data.house || 'Unallocated'} /><DetailRow label="Academic status" value={data.academic_status} /><DetailRow label="Occupation" value={data.occupation} /><DetailRow label="Marital status" value={data.marital_status} />{user.permissions.contact_information && <><DetailRow label="Email" value={data.email} /><DetailRow label="Phone" value={data.phone} /><DetailRow label="Address" value={data.address} /><DetailRow label="Date of birth" value={formatDate(data.date_of_birth)} /></>}</section>
  </>
}

function PaymentsPage() {
  const { filters, active, update, submit, setPage } = useFilters()
  const { data, loading, error, retry } = useData(`/payments/${buildQuery(active)}`)
  const { data: filterOptions } = useData('/filters/')
  return <>
    <PageHeading eyebrow="Finance operations" title="Payment monitoring" description="Read-only provider verification and reconciliation oversight. Payments cannot be marked successful from this portal." />
    <section className="ops-panel ops-list-panel"><form className="ops-filterbar" onSubmit={submit}><SearchBar value={filters.q} onChange={(value) => update('q', value)} placeholder="Search order or payment reference" /><FilterSelect label="Payment status" value={filters.status} onChange={(value) => update('status', value)} options={ [['successful', 'Successful'], ['pending', 'Pending'], ['failed', 'Failed'], ['amount_mismatch', 'Amount mismatch'], ['reconcile', 'Reconciliation required']] } /><FilterSelect label="Category" value={filters.category} onChange={(value) => update('category', value)} options={(filterOptions?.categories || []).map((item) => [item.id, item.name])} /><FilterSelect label="House" value={filters.house} onChange={(value) => update('house', value)} options={(filterOptions?.houses || []).map((item) => [item.id, item.name])} /><DateFilter label="From" value={filters.date_from} onChange={(value) => update('date_from', value)} /><DateFilter label="To" value={filters.date_to} onChange={(value) => update('date_to', value)} /><button className="ops-button ops-button-secondary" type="submit">Apply filters</button></form>{loading ? <LoadingState /> : error ? <ErrorState error={error} onRetry={retry} /> : <><PaymentTable rows={data.results} count={data.count} />{data.pages > 1 && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}</>}</section>
  </>
}

function PaymentTable({ rows, count }) {
  if (!rows?.length) return <EmptyState title="No payment attempts found" detail="Payment attempts will appear here after checkout begins." />
  return <div className="ops-table-wrap"><div className="ops-table-caption">{formatNumber(count)} payment attempts</div><table className="ops-table"><thead><tr><th>Order / payment reference</th><th>Expected</th><th>Provider amount</th><th>Verification</th><th>Provider time</th><th>Reconciliation</th></tr></thead><tbody>{rows.map((row) => <tr key={row.reference}><td><Link className="ops-reference" to={`/dic/operations/registrations/${row.order_reference}`}>{row.order_reference.slice(0, 13)}…</Link><small className="ops-cell-secondary">{row.reference}</small></td><td>{row.currency} {Number(row.expected_amount_ngn).toLocaleString('en-NG')}</td><td>{row.provider_amount_ngn ? `${row.provider_currency || row.currency} ${Number(row.provider_amount_ngn).toLocaleString('en-NG')}` : 'Unavailable'}</td><td><StatusPill value={row.verified_paid ? 'Verified paid' : row.status} positive={row.verified_paid} /></td><td>{formatDate(row.provider_paid_at, { timeStyle: 'short' })}</td><td>{row.reconciliation_reason || '—'}</td></tr>)}</tbody></table></div>
}

function HousesPage() {
  const [page, setPage] = useState(1)
  const { data, loading, error, retry } = useData(`/houses/?page=${page}`)
  const allocations = data?.allocations?.results || []
  if (loading) return <><PageHeading eyebrow="Camp readiness" title="House allocation" description="Monitor configured houses and allocations. This portal does not create or reassign allocations." /><LoadingState /></>
  return <>
    <PageHeading eyebrow="Camp readiness" title="House allocation" description="Monitor configured houses and allocations. This portal does not create or reassign allocations." />
    {error ? <ErrorState error={error} onRetry={retry} /> : <>
      {data.allocations.pages > 1 && <Pagination page={data.allocations.page} pages={data.allocations.pages} onChange={setPage} />}
      <div className="ops-summary-strip"><div><span>Eligible unallocated participants</span><strong>{formatNumber(data.eligible_unallocated)}</strong></div><div><span>Configured houses</span><strong>{formatNumber(data.houses.length)}</strong></div><div><span>Recorded allocation history</span><strong>{formatNumber(data.allocations.count || 0)}</strong></div></div>
      <section className="ops-house-grid">{data.houses.length ? data.houses.map((house) => <article className="ops-house-card" key={house.id}><span className="ops-house-icon"><Icon name="home" /></span><div><h2>{house.name}</h2><p>{statusLabel(house.gender)} <span>·</span> {statusLabel(house.status)}</p></div><strong>{formatNumber(house.allocated_count)}<small>{house.capacity ? ` / ${house.capacity}` : ' assigned'}</small></strong></article>) : <div className="ops-panel"><EmptyState title="No houses configured" detail="House names and capacities are managed by authorized administrators." /></div>}</section>
      <section className="ops-panel ops-detail-panel"><div className="ops-panel-heading"><div><span className="ops-eyebrow">ALLOCATION HISTORY</span><h2>Participant assignments</h2></div></div>{allocations.length ? <div className="ops-table-wrap"><table className="ops-table"><thead><tr><th>Participant</th><th>House</th><th>Status</th><th>Assigned</th><th>Eligibility</th></tr></thead><tbody>{allocations.map((item, index) => <tr key={`${item.participant_id}-${index}`}><td>{item.participant}</td><td>{item.house}</td><td><StatusPill value={item.status} /></td><td>{formatDate(item.allocated_at, { timeStyle: 'short' })}</td><td><StatusPill value={item.verified_eligible ? 'Verified paid' : 'Review required'} positive={item.verified_eligible} /></td></tr>)}</tbody></table></div> : <EmptyState title="No allocations recorded" detail="There are no house assignments for this edition yet." />}</section>
    </>}
  </>
}

function ReportsPage({ user }) {
  const [report, setReport] = useState('registrations')
  const [format, setFormat] = useState('docx')
  const [filters, setFilters] = useState({ q: '', payment_status: '', status: '', category: '', house: '', date_from: '', date_to: '' })
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')
  const { data: filterOptions } = useData('/filters/')
  const updateFilter = (name, value) => setFilters((current) => ({ ...current, [name]: value }))
  const reports = useMemo(() => [
    ['registrations', 'Registrations'],
    ['participants', 'Participants'],
    ...(user.permissions.finance ? [['payments', 'Payments']] : []),
    ['categories', 'Categories'],
    ['houses', 'Houses'],
    ['attention', 'Administrative attention'],
  ], [user.permissions.finance])
  const download = async () => {
    setDownloading(true)
    setError('')
    try {
      await downloadOperationsReport({ report, format, filters })
    } catch (downloadError) {
      setError(downloadError.message)
    } finally {
      setDownloading(false)
    }
  }
  return <>
    <PageHeading eyebrow="Reporting" title="Reports & exports" description="Generate permission-scoped operational reports as Word documents or spreadsheet-ready CSV." />
    <section className="ops-report-layout"><div className="ops-panel ops-report-form"><div className="ops-panel-heading"><div><span className="ops-eyebrow">REPORT BUILDER</span><h2>Configure your report</h2></div></div>
      <label className="ops-form-field">Report type<select value={report} onChange={(event) => setReport(event.target.value)}>{reports.map(([value, text]) => <option value={value} key={value}>{text}</option>)}</select></label>
      <div className="ops-form-field"><span>File format</span><div className="ops-format-options"><button className={format === 'docx' ? 'selected' : ''} onClick={() => setFormat('docx')} type="button"><b>W</b><span>Word document<small>.docx</small></span></button><button className={format === 'csv' ? 'selected' : ''} onClick={() => setFormat('csv')} type="button"><b>▦</b><span>Spreadsheet<small>.csv</small></span></button></div></div>
      <div className="ops-report-filters"><div className="ops-panel-heading"><div><span className="ops-eyebrow">OPTIONAL</span><h2>Apply filters</h2></div></div><label className="ops-form-field">Search<input value={filters.q} onChange={(event) => updateFilter('q', event.target.value)} placeholder="Reference or participant name" /></label><div className="ops-date-fields"><label className="ops-form-field">From<input type="date" value={filters.date_from} onChange={(event) => updateFilter('date_from', event.target.value)} /></label><label className="ops-form-field">To<input type="date" value={filters.date_to} onChange={(event) => updateFilter('date_to', event.target.value)} /></label></div>{['registrations', 'participants', 'payments'].includes(report) && <><label className="ops-form-field">Payment status<select value={filters.payment_status} onChange={(event) => updateFilter('payment_status', event.target.value)}><option value="">All statuses</option><option value="pending">Pending</option><option value="paid">Paid</option><option value="failed">Failed</option><option value="refunded">Refunded</option></select></label><label className="ops-form-field">Category<select value={filters.category} onChange={(event) => updateFilter('category', event.target.value)}><option value="">All categories</option>{(filterOptions?.categories || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="ops-form-field">House<select value={filters.house} onChange={(event) => updateFilter('house', event.target.value)}><option value="">All houses</option>{(filterOptions?.houses || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></>}</div>
      {error && <p className="ops-form-error" role="alert">{error}</p>}<button className="ops-button ops-button-primary ops-download-button" onClick={download} disabled={downloading || !user.permissions.export_reports}>{downloading ? 'Preparing report…' : `Download ${format.toUpperCase()}`}<Icon name="arrow" /></button><p className="ops-report-note">Exports use the same filters for both formats. Contact and finance fields are included only when your account has the relevant permission.</p>
    </div>
      <aside className="ops-panel ops-report-aside"><span className="ops-report-aside-icon"><Icon name="file" /></span><h2>Ready for the committee</h2><p>Reports include the DIC edition, generation time, applied filters and clear totals. Word reports are formatted for printing and sharing.</p><ul><li>CSV values are protected against spreadsheet formulas.</li><li>Every download is recorded in the audit activity.</li><li>Recovery codes, tokens and payment authorization URLs are never exported.</li></ul></aside>
    </section>
  </>
}

function ActivityPage() {
  const [page, setPage] = useState(1)
  const { data, loading, error, retry } = useData(`/activity/?page_size=50&page=${page}`)
  return <>
    <PageHeading eyebrow="Security & accountability" title="Activity log" description="Immutable records of sensitive administrative actions and report exports." />
    {data?.pages > 1 && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}
    <section className="ops-panel ops-list-panel">{loading ? <LoadingState /> : error ? <ErrorState error={error} onRetry={retry} /> : data.results.length ? <div className="ops-activity-list">{data.results.map((event) => <article key={event.id}><span className="ops-activity-avatar">{event.actor.slice(0, 1).toUpperCase()}</span><div><strong>{statusLabel(event.action)}</strong><p>{event.actor} · {event.target_type}{event.target_id ? ` · ${event.target_id}` : ''}</p></div><time>{formatDate(event.created_at, { timeStyle: 'short' })}</time></article>)}</div> : <EmptyState title="No activity recorded yet" detail="Sensitive admin actions and report downloads will be listed here." />}</section>
  </>
}

export default Operations
