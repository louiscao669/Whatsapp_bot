import { isReviewWorkbenchPath } from '../reviewWorkbench'

export function homePathForRole(role?: string | null, from?: string) {
  const normalized = role?.trim().toLowerCase()
  if (normalized === 'expert') {
    if (from && isReviewWorkbenchPath(from)) {
      return from
    }
    return '/review-response'
  }
  return '/analytics'
}
