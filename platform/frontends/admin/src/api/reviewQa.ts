import { apiFetch } from './client'

export type ReviewQaTab = 'unreviewed' | 'reviewed' | 'removed'

export type ReviewQaItem = {
  id: string
  chapter: string
  passage: string
  passage_text: string | null
  question_text: string
  question_type: string
  expected_answer: string
  mcq_choices: string[]
  mcq_correct_choice: string | null
  choice_slots: number
  standard_answer: string
  has_original: boolean
  qa_reviewed_at: string | null
  review_removed_at: string | null
  removed_label: string | null
  reviewed_label: string | null
  tab: string
  is_removed: boolean
}

export type ReviewQaChapter = {
  chapter: string
  count: number
  bulk_actions: string[]
  items: ReviewQaItem[]
}

export type ReviewQaDashboard = {
  tab: ReviewQaTab
  chapters: ReviewQaChapter[]
  items: ReviewQaItem[]
}

export function fetchReviewQa(tab: ReviewQaTab = 'unreviewed') {
  return apiFetch<ReviewQaDashboard>(`/api/v1/review-qa?tab=${encodeURIComponent(tab)}`)
}

export type UpdateReviewQaPayload = {
  question_text: string
  question_type: string
  expected_answer: string
  mcq_choices: string[]
  mcq_correct_choice: string
}

export function updateReviewQaItem(qaItemId: string, payload: UpdateReviewQaPayload) {
  return apiFetch<{ ok: true; message: string; item: ReviewQaItem; tab: ReviewQaTab }>(
    `/api/v1/review-qa/${qaItemId}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
  )
}

export function markReviewQaReviewed(qaItemId: string) {
  return apiFetch<{ ok: true; message: string; tab: ReviewQaTab }>(
    `/api/v1/review-qa/${qaItemId}/mark-reviewed`,
    { method: 'POST', body: '{}' },
  )
}

export function returnReviewQaUnreviewed(qaItemId: string) {
  return apiFetch<{ ok: true; message: string; tab: ReviewQaTab }>(
    `/api/v1/review-qa/${qaItemId}/return-unreviewed`,
    { method: 'POST', body: '{}' },
  )
}

export function revertReviewQaItem(qaItemId: string) {
  return apiFetch<{ ok: true; message: string; tab: ReviewQaTab }>(
    `/api/v1/review-qa/${qaItemId}/revert`,
    { method: 'POST', body: '{}' },
  )
}

export function removeReviewQaItem(qaItemId: string) {
  return apiFetch<{ ok: true; message: string; tab: ReviewQaTab }>(
    `/api/v1/review-qa/${qaItemId}/remove`,
    { method: 'POST', body: '{}' },
  )
}

export function restoreReviewQaItem(qaItemId: string) {
  return apiFetch<{ ok: true; message: string; tab: ReviewQaTab }>(
    `/api/v1/review-qa/${qaItemId}/restore`,
    { method: 'POST', body: '{}' },
  )
}

export function bulkReviewQaChapter(action: 'mark_reviewed' | 'clear_reviewed', chapter: string) {
  return apiFetch<{ ok: true; tab: ReviewQaTab; message: string }>('/api/v1/review-qa/bulk', {
    method: 'POST',
    body: JSON.stringify({ action, chapter }),
  })
}

export function bulkReviewQaAll() {
  return apiFetch<{ ok: true; tab: ReviewQaTab; message: string }>('/api/v1/review-qa/bulk', {
    method: 'POST',
    body: JSON.stringify({ action: 'mark_all_reviewed' }),
  })
}
