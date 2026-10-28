import { NavLink } from 'react-router-dom'
import { visibleOperationsGroups } from '../../services/operationsNavigation'

export default function OperationsNavigation({ user, onSelect, renderIcon }) {
  return <nav aria-label="Operations navigation">{visibleOperationsGroups(user).map((group,index) =>
    <section className="ops-nav-group" aria-labelledby={`ops-nav-group-${index}`} key={group.label}>
      <h2 id={`ops-nav-group-${index}`} className="ops-nav-group-title">{group.label}</h2>
      <div className="ops-nav-group-links">{group.items.map(item => <NavLink key={item.to} end={item.to === '/dic/operations'} to={item.to}
        onClick={onSelect} className={({ isActive }) => `ops-nav-link ${isActive ? 'is-active' : ''}`}>
        {renderIcon?.(item.icon)}<span>{item.label}</span>{item.planned && <small className="campsite-planned">Planned</small>}
      </NavLink>)}</div>
    </section>)}</nav>
}
