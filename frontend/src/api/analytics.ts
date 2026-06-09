import { apiFetch } from './client'

export type AnalyticsSummary = {
  participants: number
  qa_items: number
  responses: number
  flagged: number
  average_score: string | null
}

export type AnalyticsResponseCountRow = {
  qa_item_id: string
  passage: string
  question: string
  response_count: number
  min_required: number
  meets_target: boolean
}

export type AnalyticsPerQaRow = {
  passage: string
  question: string
  responses: number
  flagged: number
  flag_rate: number | null
  average_score: string | null
}

export type AnalyticsDashboard = {
  summary: AnalyticsSummary
  response_counts: AnalyticsResponseCountRow[]
  per_qa_metrics: AnalyticsPerQaRow[]
}

export function fetchAnalytics() {
  return apiFetch<AnalyticsDashboard>('/api/v1/analytics')
}
