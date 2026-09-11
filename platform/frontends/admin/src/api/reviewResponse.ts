import { apiFetch } from './client'

export type ReviewResponseItem = {
  response_id: string
  qa_item_id: string
  language: string
  passage: string
  passage_text: string
  question: string
  expected_answer_en: string
  keywords: { required: string[]; optional: string[] }
  question_target_audio: { recording_id: string; media_url: string } | null
  answer: {
    response_type: string
    text: string
    transcript: string
    audio_url: string | null
  }
  score: string | null
  is_correct: string
  review_status: string
}

export type ReviewResponseDashboard = {
  language: string | null
  language_options: string[]
  items: ReviewResponseItem[]
}

export function fetchReviewResponse(language?: string) {
  const params = language ? `?language=${encodeURIComponent(language)}` : ''
  return apiFetch<ReviewResponseDashboard>(`/api/v1/review-response${params}`)
}

export function submitReviewResponseDecision(responseId: string, decision: 'correct' | 'incorrect') {
  return apiFetch<{ ok: true; message: string }>(
    `/api/v1/review-response/${responseId}/decision`,
    {
      method: 'POST',
      body: JSON.stringify({ decision }),
    },
  )
}
