import { ApiError, apiFetch } from './client'

export type QaItemRow = {
  id: string
  passage: string
  question: string
  question_type: string
  review_status: string
  review_tab: string
  response_count: number
  flagged_count: number
  average_score: string | null
  min_responses_required: number
  review_priority: number
  active: boolean
}

export type QaItemChoice = {
  letter: string
  text: string
  is_correct: boolean
}

export type QaItemExpectedAnswer =
  | { kind: 'open'; text: string }
  | { kind: 'mcq' | 'tf'; correct_choice: string | null; choices: QaItemChoice[] }

export type QaItemPromptRecording = {
  id: string
  language: string
  recording_type: string
  version: number
  media_url: string
  created_at: string | null
}

export type QaItemDetail = {
  id: string
  passage_id: string
  passage: string
  passage_text: string | null
  question_type: string
  question_text: string
  expected_answer: QaItemExpectedAnswer
  review_status: string
  review_tab: string
  qa_reviewed_at: string | null
  review_removed_at: string | null
  active: boolean
  settings: {
    min_responses_required: number
    review_priority: number
    required_keywords: string[]
    optional_keywords: string[]
    keyword_source: string
  }
  prompt_recordings: {
    language: string | null
    question: QaItemPromptRecording | null
    answer: QaItemPromptRecording | null
  }
  analytics: {
    total_responses: number
    flagged_count: number
    flag_rate: number | null
    average_score: string | null
    scored_count: number
    meets_min_responses: boolean
    responses_needed: number
  }
  created_at: string | null
  updated_at: string | null
}

export function fetchQaItems() {
  return apiFetch<{ items: QaItemRow[] }>('/api/v1/qa-items')
}

export function fetchQaItemDetail(qaItemId: string, language?: string) {
  const params = language ? `?language=${encodeURIComponent(language)}` : ''
  return apiFetch<{ item: QaItemDetail }>(`/api/v1/qa-items/${qaItemId}${params}`)
}

export type QaItemStatsSummaryCard = {
  label: string
  count: number
}

export type QaItemStatsBarRow = {
  letter: string
  count: number
  is_correct: boolean
}

export type QaItemStatsParticipantRow = {
  participant: string
  language: string
  received_at: string
  response_type: string
  answer: string
  correctness: string
}

export type QaItemStats = {
  qa_item_id: string
  question_type: string
  total_responses: number
  selected_languages: string[]
  language_options: string[]
  summary_cards: QaItemStatsSummaryCard[]
  bar_chart: QaItemStatsBarRow[]
  correct_choice: string | null
  participants: QaItemStatsParticipantRow[]
}

export function fetchQaItemStats(qaItemId: string, languages: string[] = []) {
  const params = new URLSearchParams()
  for (const language of languages) {
    params.append('languages', language)
  }
  const query = params.toString()
  return apiFetch<{ stats: QaItemStats }>(
    `/api/v1/qa-items/${qaItemId}/stats${query ? `?${query}` : ''}`,
  )
}

export type AssignParticipant = {
  id: string
  display_name: string | null
  wa_id: string
  target_language: string | null
}

export function fetchAssignParticipants() {
  return apiFetch<{ participants: AssignParticipant[] }>('/api/v1/qa-items/participants')
}

export function fetchImportTemplate() {
  return apiFetch<{ template: string; hint: string }>('/api/v1/qa-items/import-template')
}

export type ImportQaItemsPayload = {
  json_text: string
  skip_existing?: boolean
  defaults?: {
    min_responses_required?: number
    review_priority?: number
    active?: boolean
  }
}

export type ImportQaItemsResult = {
  ok: true
  created: number
  skipped: number
  errors: string[]
  message: string
}

export function importQaItems(payload: ImportQaItemsPayload) {
  return apiFetch<ImportQaItemsResult>('/api/v1/qa-items/import', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function importQaItemsFromFile(
  file: File,
  options: {
    skip_existing?: boolean
    defaults?: ImportQaItemsPayload['defaults']
  } = {},
) {
  const formData = new FormData()
  formData.append('json_file', file)
  formData.append('skip_existing', options.skip_existing === false ? '0' : '1')
  formData.append(
    'import_min_responses_required',
    String(options.defaults?.min_responses_required ?? 3),
  )
  formData.append('import_review_priority', String(options.defaults?.review_priority ?? 0))
  formData.append('import_active', options.defaults?.active === false ? '0' : '1')

  const response = await fetch('/api/v1/qa-items/import', {
    method: 'POST',
    body: formData,
    credentials: 'include',
  })
  const payload = (await response.json().catch(() => ({}))) as ImportQaItemsResult & {
    message?: string
    error?: string
  }
  if (!response.ok) {
    throw new ApiError(payload.message ?? response.statusText, response.status, payload.error)
  }
  return payload
}

export function bulkQaItemsAction(payload: {
  action: 'delete' | 'assign'
  qa_item_ids: string[]
  participant_id?: string
}) {
  return apiFetch<{ ok: true; action: string; count: number; message: string }>(
    '/api/v1/qa-items/bulk',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export function deleteQaItem(qaItemId: string) {
  return apiFetch<{ ok: true; message: string }>(`/api/v1/qa-items/${qaItemId}`, {
    method: 'DELETE',
  })
}

export type UpdateQaItemSettingsPayload = {
  min_responses_required: number
  review_priority: number
  required_keywords: string[]
  optional_keywords: string[]
  new_required_keywords?: string
  new_optional_keywords?: string
  regenerate_required_keywords?: boolean
}

export function updateQaItemSettings(qaItemId: string, payload: UpdateQaItemSettingsPayload) {
  return apiFetch<{ ok: true; message: string; item: QaItemDetail }>(
    `/api/v1/qa-items/${qaItemId}/settings`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  )
}

export type QaItemOpenResponse = {
  received_at: string
  participant: string
  language: string
  response_type: string
  answer: string
  normalized_text: string
  correctness_score: string | null
  matched_keywords: string[]
  missing_keywords: string[]
  is_correct: string
  correctness_label: string
  flag_reason: string
  review_status: string
  audio_url: string | null
}

export type QaItemChoiceResponse = {
  received_at: string
  participant: string
  language: string
  response_type: string
  choice_answer: string
  correctness: string
  audio_url: string | null
}

export type QaItemResponsesPayload = {
  qa_item_id: string
  question_type: string
  choice_scored: boolean
  languages: string[]
  responses: QaItemOpenResponse[] | QaItemChoiceResponse[]
}

export type QaItemAssignmentRow = {
  participant: string
  wa_id: string
  language: string
  status: string
  assigned_at: string | null
  completed_at: string | null
  batch_id: string
}

export function fetchQaItemResponses(qaItemId: string, languages: string[] = []) {
  const params = new URLSearchParams()
  for (const language of languages) {
    params.append('languages', language)
  }
  const query = params.toString()
  return apiFetch<QaItemResponsesPayload>(
    `/api/v1/qa-items/${qaItemId}/responses${query ? `?${query}` : ''}`,
  )
}

export function fetchQaItemAssignments(qaItemId: string, languages: string[] = []) {
  const params = new URLSearchParams()
  for (const language of languages) {
    params.append('languages', language)
  }
  const query = params.toString()
  return apiFetch<{ assignments: QaItemAssignmentRow[]; languages: string[] }>(
    `/api/v1/qa-items/${qaItemId}/assignments${query ? `?${query}` : ''}`,
  )
}

export function assignQaItem(qaItemId: string, participantId: string) {
  return apiFetch<{ ok: true; message: string }>(`/api/v1/qa-items/${qaItemId}/assign`, {
    method: 'POST',
    body: JSON.stringify({ participant_id: participantId }),
  })
}
