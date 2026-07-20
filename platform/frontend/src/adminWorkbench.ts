export const ADMIN_MAIN_TABS = [
  { label: 'Analytics', path: '/analytics', prefix: '/analytics' },
  { label: 'Passages', path: '/passages', prefix: '/passages' },
  { label: 'Questions', path: '/qa-items/list', prefix: '/qa-items' },
  { label: 'Participants', path: '/participants', prefix: '/participants' },
] as const

export const ADMIN_EXPORT_TAB = {
  label: 'Export',
  path: '/export/responses',
  prefix: '/export',
} as const

export const ADMIN_WORKBENCH_TABS = [...ADMIN_MAIN_TABS, ADMIN_EXPORT_TAB] as const

export const ADMIN_EXPORT_SUBTABS = [
  { label: 'Export responses', path: '/export/responses' },
  { label: 'Export flagged', path: '/export/flagged' },
  { label: 'Export audio', path: '/export/audio' },
] as const

export function isAdminWorkbenchPath(pathname: string) {
  return ADMIN_WORKBENCH_TABS.some(
    (tab) => pathname === tab.prefix || pathname.startsWith(`${tab.prefix}/`),
  )
}
