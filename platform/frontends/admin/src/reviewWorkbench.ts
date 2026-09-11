export const REVIEW_WORKBENCH_TABS = [
  { label: 'Review Response', path: '/review-response' },
  { label: 'Review QA', path: '/review-qa' },
  { label: 'Record', path: '/record' },
] as const

export const REVIEW_WORKBENCH_PATHS = REVIEW_WORKBENCH_TABS.map((tab) => tab.path)

export function isReviewWorkbenchPath(pathname: string) {
  return REVIEW_WORKBENCH_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  )
}

const REVIEW_NAV_LABELS = new Set([
  'Review',
  'Review Response',
  'Review QA',
  'Record',
])

export function isReviewNavPage(page: { label: string; path: string }) {
  return REVIEW_NAV_LABELS.has(page.label) || isReviewWorkbenchPath(page.path)
}
