export const ADMIN_MAIN_TABS = [
  { label: 'Analytics', path: '/analytics', prefix: '/analytics' },
  { label: 'QA Items', path: '/qa-items/list', prefix: '/qa-items' },
  { label: 'Participants', path: '/participants', prefix: '/participants' },
] as const

export const ADMIN_EXPORT_TAB = {
  label: 'Export',
  path: '/export/responses',
  prefix: '/export',
} as const

export const ADMIN_WORKBENCH_TABS = [...ADMIN_MAIN_TABS, ADMIN_EXPORT_TAB] as const

export const ADMIN_QA_ITEMS_SUBTABS = [
  { label: 'Add QAs', path: '/qa-items/add' },
  { label: 'QAs', path: '/qa-items/list' },
] as const

export function isQaItemsListPath(pathname: string) {
  if (pathname === '/qa-items/list') {
    return true
  }
  const match = pathname.match(/^\/qa-items\/([^/]+)$/)
  return Boolean(match && match[1] !== 'add' && match[1] !== 'list')
}

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
