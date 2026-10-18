export const navigation = [
  { label: 'Overview', to: '/dic/operations', icon: 'grid' },
  { label: 'Registrations', to: '/dic/operations/registrations', icon: 'clipboard' },
  { label: 'Participants', to: '/dic/operations/participants', icon: 'users' },
  { label: 'Payments', to: '/dic/operations/payments', icon: 'card', permission: 'finance' },
  { label: 'House allocation', to: '/dic/operations/houses', icon: 'home' },
  { label: 'Reports', to: '/dic/operations/reports', icon: 'file', permission: 'export_reports' },
  { label: 'Activity', to: '/dic/operations/activity', icon: 'activity', permission: 'audit' },
]

export function visibleOperationsNavigation(user) {
  return navigation.filter((item) => !item.permission || user.permissions[item.permission])
}
