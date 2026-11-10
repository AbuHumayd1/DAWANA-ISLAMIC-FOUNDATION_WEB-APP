export const navigation = [
  { label: 'Timetables', to: '/dic/operations/timetables', icon: 'clipboard', permission: 'timetables' },
  { label: 'Classes', to: '/dic/operations/classes', icon: 'users', permission: 'classes', campsite: true },
  { label: 'Announcements', to: '/dic/operations/announcements', icon: 'clipboard', permission: 'announcements', campsite: true },
  { label: 'Overview', to: '/dic/operations', icon: 'grid' },
  { label: 'Camp Check-in', to: '/dic/operations/check-in', icon: 'clipboard', campsite: true },
  { label: 'Finance', to: '/dic/operations/finance', icon: 'card', permission: 'finance', campsite: true },
  { label: 'ID Card Printing', to: '/dic/operations/id-printing', icon: 'card', permission: 'manage_ids' },
  { label: 'Participant IDs', to: '/dic/operations/participant-ids', icon: 'users', permission: 'ids' },
  { label: 'Assisted registration', to: '/dic/operations/assisted-registration', icon: 'clipboard', campsite: true },
  { label: 'Registrations', to: '/dic/operations/registrations', icon: 'clipboard' },
  { label: 'Participants', to: '/dic/operations/participants', icon: 'users' },
  { label: 'Payments', to: '/dic/operations/payments', icon: 'card', permission: 'finance' },
  { label: 'House allocation', to: '/dic/operations/houses', icon: 'home' },
  { label: 'Reports', to: '/dic/operations/reports', icon: 'file', permission: 'export_reports' },
  { label: 'House scoring', to: '/dic/operations/scoring', icon: 'activity', campsite: true, permission: 'scores' },
  { label: 'Feedback', to: '/dic/operations/feedback', icon: 'clipboard', campsite: true, permission:'feedback' },
  { label: 'Submit feedback', to: '/dic/operations/feedback-submit', icon:'clipboard',campsite:true,permission:'feedback_entry' },
  { label: 'Welfare complaints', to: '/dic/operations/welfare', icon:'clipboard',campsite:true,permission:'welfare' },
  { label: 'Comprehensive reporting', to: '/dic/operations/reporting-hub', icon: 'file', campsite: true, permission:'export_reports' },
  { label: 'Registration overview', to: '/dic/operations/registration-overview', icon: 'grid', campsite: true },
  { label: 'Activity Log', to: '/dic/operations/activity', icon: 'activity', permission: 'audit' },
]

export function visibleOperationsNavigation(user) {
  return navigation.filter((item) => (!item.campsite || user.can_access_campsite)
    && (!item.permission || user.permissions[item.permission]))
}

export const operationsNavigationGroups = [
  { label: 'Camp Overview', paths: ['', 'registration-overview'] },
  { label: 'Participants & Registration', paths: ['check-in', 'assisted-registration', 'registrations', 'participants', 'participant-ids', 'id-printing', 'houses'] },
  { label: 'Camp Activities', paths: ['classes', 'timetables', 'announcements', 'scoring', 'feedback','feedback-submit','welfare'] },
  { label: 'Finance & Reports', paths: ['payments', 'finance', 'reports', 'reporting-hub'] },
  { label: 'Administration', paths: ['activity'] },
]

export function visibleOperationsGroups(user) {
  const allowed = new Map(visibleOperationsNavigation(user).map(item => [item.to, item]))
  return operationsNavigationGroups.map(group => ({ label: group.label,
    items: group.paths.map(path => allowed.get(`/dic/operations${path ? `/${path}` : ''}`)).filter(Boolean),
  })).filter(group => group.items.length)
}
