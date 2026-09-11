import { apiFetch } from './client'

export type AssignmentTranslationOption = {
  id: string
  name: string | null
  label: string
}

export type ParticipantAssignmentQuestion = {
  id: string
  passage: string
  question: string
  question_type: string
  chapter_number: number
  verse_number: number
  translations: AssignmentTranslationOption[]
}

export type ParticipantRow = {
  id: string
  participant_id: string
  display_name: string
  language: string
  session_state: string
  current_question: string
  assigned_questions: string
  questions_completed: number
  correct: number
  incorrect: number
  under_review: number
  batch_size: number
  last_seen: string | null
  consented: boolean
}

export type ParticipantHistoryRow = {
  qa_item_id: string
  passage: string
  question: string
  question_type: string
  expected_answer: string
  user_answer: string
  correctness_status: string
}

export type ParticipantAssignedQuestionRow = {
  assignment_id: string
  qa_item_id: string
  passage: string
  question: string
  translation_name: string | null
  passage_verse_numbers: string[]
  batch_id: string | null
  status: string
  assigned_at: string | null
}

export type ParticipantDetail = {
  participant: {
    id: string
    participant_id: string
    display_name: string
    language: string
    session_state: string
    current_question: string | null
    assigned_questions: string | null
    questions_completed: number
    correct: number
    incorrect: number
    under_review: number
    batch_size: number
    last_seen: string | null
    consented: boolean
    created_at: string | null
  }
  assigned_questions: ParticipantAssignedQuestionRow[]
  history: ParticipantHistoryRow[]
}

export function fetchParticipants() {
  return apiFetch<{ participants: ParticipantRow[] }>('/api/v1/participants')
}

export function fetchParticipantDetail(participantId: string) {
  return apiFetch<ParticipantDetail>(`/api/v1/participants/${participantId}`)
}

export function updateParticipantLanguage(participantId: string, language: string) {
  return apiFetch<ParticipantDetail & { ok: true; message: string }>(
    `/api/v1/participants/${participantId}/language`,
    {
      method: 'PATCH',
      body: JSON.stringify({ language }),
    },
  )
}

export function fetchParticipantAssignmentOptions(participantId: string) {
  return apiFetch<{
    participant_language: string
    questions: ParticipantAssignmentQuestion[]
  }>(`/api/v1/participants/${participantId}/assignment-options`)
}

export function assignParticipantQuestions(
  participantId: string,
  selections: { qa_item_id: string; translation_id: string }[],
) {
  return apiFetch<{ ok: true; assigned_count: number; message: string }>(
    `/api/v1/participants/${participantId}/assignments`,
    {
      method: 'POST',
      body: JSON.stringify({ selections }),
    },
  )
}

export function skipParticipantAssignment(participantId: string, assignmentId: string) {
  return apiFetch<{ ok: true; message: string }>(
    `/api/v1/participants/${participantId}/assignments/${assignmentId}`,
    { method: 'DELETE' },
  )
}
