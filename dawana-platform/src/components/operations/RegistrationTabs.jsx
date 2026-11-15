import { Link, useSearchParams } from 'react-router-dom'

const views = [
  ['active', 'Active', 'Current registrations'],
  ['all', 'All non-deleted', 'Active and archived records'],
  ['archived', 'Archived', 'Records set aside'],
  ['trash', 'Trash / Restore', 'Review deleted records'],
]

export default function RegistrationTabs({ canRestore = false }) {
  const [params] = useSearchParams()
  const selected = params.get('archive') || 'active'
  return <nav className="ops-registration-tabs" aria-label="Registration records">
    {views.filter(([key]) => key !== 'trash' || canRestore).map(([key, label, detail]) => {
      const next = new URLSearchParams(params)
      next.delete('page')
      if (key === 'active') next.delete('archive')
      else next.set('archive', key)
      return <Link key={key} className="ops-registration-tab"
        aria-current={selected === key ? 'page' : undefined}
        to={'/dic/operations/registrations' + (next.size ? '?' + next : '')}>
        <strong>{label}</strong><span>{detail}</span>
      </Link>
    })}
  </nav>
}
