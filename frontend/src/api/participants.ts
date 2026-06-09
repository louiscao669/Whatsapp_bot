import { apiFetch } from './client'

export type ParticipantRow = {
  id: string
  wa_id: string
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

export type ParticipantDetail = {
  participant: {
    id: string
    wa_id: string
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
  history: ParticipantHistoryRow[]
}

export function fetchParticipants() {
  return apiFetch<{ participants: ParticipantRow[] }>('/api/v1/participants')
}

export function fetchParticipantDetail(participantId: string) {
  return apiFetch<ParticipantDetail>(`/api/v1/participants/${participantId}`)
}
