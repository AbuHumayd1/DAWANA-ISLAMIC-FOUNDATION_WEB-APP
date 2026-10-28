// Future capabilities are plans, never grants or implemented transaction endpoints.
export const campsiteModules = {
  'reporting-hub': {
    implemented: true,
    permission: 'export_reports',
    title: 'Comprehensive reporting',
    summary: 'Bring camp results together in one report.',
    available: 'Unified reporting, CSV and printable reports are available to authorized report users. Domain permissions and approved schemas remain required.',
    planned: [],
    approvals: 'Academic allocations and unavailable schema are reported explicitly. Phase 4 timetables remain postponed.',
  },
}

export function campsiteMetricValue(value) {
  return Number.isInteger(value) && value >= 0 ? new Intl.NumberFormat('en-NG').format(value) : 'Unavailable'
}

export function campsiteOverviewPath(edition = '') {
  if (edition && !/^[1-9]\d*$/.test(String(edition))) throw new Error('Choose a valid camp edition.')
  return `/campsite/${edition ? `?edition=${encodeURIComponent(edition)}` : ''}`
}
