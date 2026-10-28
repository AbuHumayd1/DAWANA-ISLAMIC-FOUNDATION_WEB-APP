export function MoreFilters({ children, label = 'More filters' }) {
  return <details className="ops-more-filters"><summary>{label}</summary><div className="ops-secondary-filters">{children}</div></details>
}

export function FilterActions({ onClear }) {
  return <div className="ops-filter-actions"><button className="ops-button ops-button-primary" type="submit">Apply filters</button>
    <button className="ops-button ops-button-secondary" type="button" onClick={onClear}>Clear filters</button></div>
}

export function HelpDetails({ children, label = 'About these figures' }) {
  return <details className="ops-help"><summary>{label}</summary><div>{children}</div></details>
}
